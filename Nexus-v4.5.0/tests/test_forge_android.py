"""Testes do módulo Android do Forge (core/forge_android.py + a parte Android de core/forge_engine.py e
actions/forge_app.py).

Não há Android Studio aqui: o JDK, o SDK, o Gradle e o adb são scripts de mentira (sh) que registram o que
receberam e criam um "APK" de mentira. Ou seja: estes testes provam a lógica do Forge (detecção, listas
fechadas, ordem das chamadas, entrega do APK), NÃO que um build Android real passa — isso só no PC do usuário.
"""
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from actions import forge_app as FA
from core import forge_android as AND
from core import forge_engine as FE

pytestmark = pytest.mark.skipif(os.name == "nt", reason="usa scripts sh como ferramentas de mentira")

GRADLE_FALSO = """#!/bin/sh
if [ "$1" = "wrapper" ]; then
cat > gradlew <<'EOS'
#!/bin/sh
echo "gradlew $@ | chave=${ANTHROPIC_API_KEY:-nenhuma} | java=$JAVA_HOME | sdk=$ANDROID_HOME"
mkdir -p app/build/outputs/apk/debug
echo apk-de-mentira > app/build/outputs/apk/debug/app-debug.apk
exit 0
EOS
chmod +x gradlew
echo @echo off > gradlew.bat
mkdir -p gradle/wrapper
echo distributionUrl=gradle > gradle/wrapper/gradle-wrapper.properties
echo jar > gradle/wrapper/gradle-wrapper.jar
fi
"""

ADB_FALSO = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/adb.log"
[ "$1" = "-s" ] && { shift; shift; }
case "$1" in
  devices) printf 'List of devices attached\\n'; cat "$(dirname "$0")/devices.txt" ;;
  install) echo Performing Streamed Install; echo Success ;;
  *) echo ok ;;
esac
"""


def _tf():
    """Reaproveita os auxiliares do test_forge.py (que roda como módulo solto, sem pacote tests/)."""
    try:
        from tests import test_forge as tf
    except ImportError:
        import test_forge as tf
    return tf


def _script(caminho: Path, texto: str):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    caminho.chmod(caminho.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _java(raiz: Path, versao: str = "17.0.9") -> Path:
    home = raiz / "jdk"
    _script(home / "bin" / "java", f"#!/bin/sh\necho 'openjdk version \"{versao}\" 2024-01-16' >&2\n")
    return home


@pytest.fixture
def kit(tmp_path):
    """Um 'PC' de mentira completo: JDK 17, SDK com licença e plataforma, adb, Gradle e um celular."""
    sdk = tmp_path / "sdk"
    (sdk / "licenses").mkdir(parents=True)
    (sdk / "licenses" / "android-sdk-license").write_text("ok")
    (sdk / "platforms" / "android-34").mkdir(parents=True)
    _script(sdk / "platform-tools" / "adb", ADB_FALSO)
    (sdk / "platform-tools" / "devices.txt").write_text("SER123\tdevice\n")
    gradle_dir = tmp_path / "gradlebin"
    _script(gradle_dir / "gradle", GRADLE_FALSO)
    jdk = _java(tmp_path)
    env = {"PATH": f"{gradle_dir}:/usr/bin:/bin", "ANDROID_HOME": str(sdk), "JAVA_HOME": str(jdk)}
    home = tmp_path / "home"
    home.mkdir()
    return SimpleNamespace(sdk=sdk, env=env, home=home, jdk=jdk, adb_log=sdk / "platform-tools" / "adb.log",
                           devices=sdk / "platform-tools" / "devices.txt", tmp=tmp_path)


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(FA, "PROJECTS_DIR", tmp_path / "NexusForge")
    monkeypatch.setattr(FA, "_cache", {})
    monkeypatch.setattr(FE, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(FE.NexusForge, "_venv_python", lambda self: sys.executable)
    FA._msgs.clear()
    FA._ativo.clear()
    yield
    FA._msgs.clear()


def usar_kit(monkeypatch, kit):
    monkeypatch.setattr(FE.NexusForge, "_toolchain", lambda self: AND.detectar(kit.env, kit.home))


def usar_pc_vazio(monkeypatch, tmp_path):
    vazio = {"PATH": ""}
    monkeypatch.setattr(FE.NexusForge, "_toolchain", lambda self: AND.detectar(vazio, tmp_path / "vazio"))


PLANO_ANDROID = {"titulo": "8 Ways Navegacao", "resumo": "Navegador por voz.", "stack": "Kotlin + Jetpack Compose",
                 "plataforma": "android", "pacote": "com.nexus.oitovias", "arquivos": ["app/build.gradle.kts"],
                 "entrada": "", "comando_teste": "", "como_executar": "instale o APK", "riscos": []}


def motor(tmp_path, falas=None):
    falas = [] if falas is None else falas
    return FE.NexusForge(falar=falas.append, ouvir=lambda: "", pasta_projetos=tmp_path / "raiz",
                         progresso_voz=False, segundo_plano=False)


def projeto_android(tmp_path, plano=None):
    m = motor(tmp_path)
    m.plano = dict(plano or PLANO_ANDROID, apk=AND.APK_PADRAO)
    m.pasta = m._pasta_nova("oito-vias")
    m._iniciar_projeto(m.plano, "x")
    return m


# ── detecção do ambiente ─────────────────────────────────────────────────────

def test_versao_do_java_lida_dos_formatos_conhecidos():
    assert AND.parse_versao_java('openjdk version "17.0.9" 2023') == 17
    assert AND.parse_versao_java('java version "1.8.0_392"') == 8
    assert AND.parse_versao_java('openjdk version "21" 2023-09-19') == 21
    assert AND.parse_versao_java("nada") is None


def test_pc_completo_nao_falta_nada(kit):
    tc = AND.detectar(kit.env, kit.home)
    assert tc.faltando_para(None) == [] and tc.ok
    assert tc.java_versao == 17 and tc.adb and tc.gradle and tc.licencas and tc.plataforma
    assert "pronto" in AND.resumo(tc)


def test_pc_vazio_diz_o_que_falta_em_portugues(tmp_path):
    tc = AND.detectar({"PATH": ""}, tmp_path / "vazio")
    texto = " ".join(tc.faltando_para(None))
    assert "Android SDK" in texto and "JDK" in texto and "Gradle" in texto
    assert not tc.ok


def test_jdk_antigo_e_recusado(kit):
    kit.env["JAVA_HOME"] = str(_java(kit.tmp / "velho", "11.0.2"))
    kit.env["PATH"] = str(kit.tmp / "gradlebin")        # sem outro java no PATH para "salvar" o teste
    tc = AND.detectar(kit.env, kit.home)
    assert any("mais novo" in f and "11" in f for f in tc.base)


def test_sem_licencas_do_sdk_avisa(kit):
    (kit.sdk / "licenses" / "android-sdk-license").unlink()
    assert any("licenças" in f for f in AND.detectar(kit.env, kit.home).base)


def test_gradle_solto_nao_e_preciso_se_o_projeto_ja_tem_gradlew(kit, tmp_path):
    kit.env["PATH"] = "/usr/bin:/bin"
    tc = AND.detectar(kit.env, kit.home)
    assert tc.faltando_para(None) and tc.gradle is None
    pasta = tmp_path / "p"
    pasta.mkdir()
    (pasta / "gradlew").write_text("x")
    assert tc.faltando_para(pasta) == []


def test_ambiente_do_processo_filho_leva_java_sdk_e_adb(kit):
    tc = AND.detectar(kit.env, kit.home)
    env = AND.ambiente(tc, {"PATH": "/usr/bin"})
    assert env["JAVA_HOME"] == str(kit.jdk) and env["ANDROID_HOME"] == str(kit.sdk)
    assert str(kit.sdk / "platform-tools") in env["PATH"] and str(kit.jdk / "bin") in env["PATH"]


def test_lista_dispositivos_com_estado(kit):
    kit.devices.write_text("SER123\tdevice\nXYZ\tunauthorized\n")
    tc = AND.detectar(kit.env, kit.home)
    assert AND.listar_dispositivos(tc.adb) == [("SER123", "device"), ("XYZ", "unauthorized")]


# ── preparar o projeto ───────────────────────────────────────────────────────

def test_wrapper_e_arquivos_do_projeto_sao_criados(kit, tmp_path):
    tc = AND.detectar(kit.env, kit.home)
    pasta = tmp_path / "proj"
    pasta.mkdir()
    msgs = AND.preparar_projeto(pasta, tc, AND.ambiente(tc, os.environ))
    assert (pasta / "gradlew").is_file() and os.access(pasta / "gradlew", os.X_OK)
    assert (pasta / "gradle" / "wrapper" / "gradle-wrapper.jar").is_file()
    assert (pasta / "local.properties").read_text().strip() == f"sdk.dir={kit.sdk.as_posix()}"
    assert "android.useAndroidX=true" in (pasta / "gradle.properties").read_text()
    gi = (pasta / ".gitignore").read_text().split()
    assert "local.properties" in gi and ".gradle/" in gi
    assert not any(m.startswith("ERRO") for m in msgs)


def test_gradle_properties_do_construtor_nao_e_sobrescrito(kit, tmp_path):
    tc = AND.detectar(kit.env, kit.home)
    pasta = tmp_path / "proj"
    pasta.mkdir()
    (pasta / "gradle.properties").write_text("meu=1\n")
    AND.preparar_projeto(pasta, tc, AND.ambiente(tc, os.environ))
    assert (pasta / "gradle.properties").read_text() == "meu=1\n"


def test_sem_gradle_o_wrapper_nao_e_gerado_e_diz_por_que(kit, tmp_path):
    kit.env["PATH"] = "/usr/bin:/bin"
    tc = AND.detectar(kit.env, kit.home)
    ok, msg = AND.gerar_wrapper(tmp_path, tc, os.environ)
    assert not ok and "Gradle" in msg


# ── listas fechadas ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("args", [["assembleDebug"], ["testDebugUnitTest", "assembleDebug"],
                                  [":app:assembleDebug", "--stacktrace"], ["clean"], ["lintDebug", "--offline"]])
def test_gradle_aceita_o_basico(args):
    assert AND.validar_gradle(args) is None


@pytest.mark.parametrize("args", [[], ["--stacktrace"], ["publish"], ["assembleRelease"], ["tasks", "--all"],
                                  ["assembleDebug", "-Pkey=1"], ["assembleDebug", "--init-script", "x.gradle"],
                                  ["-c", "outro.kts", "assembleDebug"], ["assembleDebug;rm"]])
def test_gradle_recusa_o_resto(args):
    assert AND.validar_gradle(args)


def test_adb_aceita_so_o_permitido(tmp_path):
    pasta = tmp_path / "p"
    (pasta / "app").mkdir(parents=True)
    (pasta / "app" / "x.apk").write_text("a")
    assert AND.validar_adb(["devices"], pasta) == ["devices"]
    assert AND.validar_adb(["-s", "SER1", "install", "-r", "app/x.apk"], pasta)[-1] == str((pasta / "app" / "x.apk").resolve())
    assert AND.validar_adb(["logcat", "-d", "-t", "50", "*:E"], pasta)
    assert AND.validar_adb(["shell", "am", "start", "-n", "com.a.b/.MainActivity"], pasta)
    assert AND.validar_adb(["shell", "monkey", "-p", "com.a.b", "-c", "android.intent.category.LAUNCHER", "1"], pasta)
    assert AND.validar_adb(["uninstall", "com.a.b"], pasta, "com.a.b")


@pytest.mark.parametrize("args", [
    ["shell", "rm", "-rf", "/sdcard"], ["shell", "pm", "uninstall", "com.x"], ["push", "a", "/sdcard/a"],
    ["pull", "/data/x", "."], ["reboot"], ["logcat"], ["install", "../fora.apk"], ["install", "/etc/passwd"],
    ["install", "-g", "app/x.apk"], ["uninstall", "com.outro.app"], ["shell"], ["-s", "a;b", "devices"],
    ["shell", "am", "start", "-n", "com.a.b/.Main; rm -rf /"], ["tcpip", "5555"], [],
])
def test_adb_recusa_o_perigoso(tmp_path, args):
    pasta = tmp_path / "p"
    (pasta / "app").mkdir(parents=True)
    (pasta / "app" / "x.apk").write_text("a")
    with pytest.raises(ValueError):
        AND.validar_adb(args, pasta, "com.a.b")


def test_adb_recusa_apk_que_nao_existe(tmp_path):
    with pytest.raises(ValueError, match="compile primeiro"):
        AND.validar_adb(["install", "-r", "app/nao.apk"], tmp_path)


def test_pacote_padrao_e_valido():
    assert AND.pacote_padrao("8 Ways Navegação") == "com.nexus.app8waysnavegacao"
    assert AND.pacote_padrao("Çá!") == "com.nexus.ca"
    assert AND.PACOTE.match(AND.pacote_padrao("???"))


# ── plano ────────────────────────────────────────────────────────────────────

def _plano_do_arquiteto(tmp_path, monkeypatch, plano: dict):
    TF = _tf()
    ClienteFalso, resp, tx = TF.ClienteFalso, TF.resp, TF.tx
    m = motor(tmp_path)
    m._cliente_cache = ClienteFalso([resp([tx(json.dumps(plano))], "end_turn")])
    return m.planejar("quero um app android de navegação")


def test_plano_android_e_completado_pelo_motor(tmp_path, monkeypatch):
    plano = _plano_do_arquiteto(tmp_path, monkeypatch, {
        "titulo": "8 Ways", "resumo": "x", "stack": "Kotlin + Compose", "plataforma": "android",
        "pacote": "Pacote Inválido!", "comando_teste": "python -m pytest", "entrada": "main.py"})
    assert plano["plataforma"] == "android"
    assert AND.PACOTE.match(plano["pacote"]) and plano["pacote"].startswith("com.nexus.")
    assert plano["comando_teste"] == "gradlew testDebugUnitTest assembleDebug" and plano["entrada"] == ""
    assert plano["apk"] == AND.APK_PADRAO and any("primeiro build" in r for r in plano["riscos"])


def test_plano_comum_nao_vira_android(tmp_path, monkeypatch):
    plano = _plano_do_arquiteto(tmp_path, monkeypatch, {
        "titulo": "Tarefas", "resumo": "x", "stack": "Python + Tkinter", "plataforma": "desktop",
        "comando_teste": "python -m py_compile main.py", "entrada": "main.py"})
    assert plano["plataforma"] == "desktop" and "pacote" not in plano
    assert plano["comando_teste"] == "python -m py_compile main.py"


def test_plataforma_ausente_com_kotlin_e_android_e_reconhecida(tmp_path, monkeypatch):
    plano = _plano_do_arquiteto(tmp_path, monkeypatch, {
        "titulo": "Mapa Android", "resumo": "x", "stack": "Android com Kotlin e Compose"})
    assert plano["plataforma"] == "android"


# ── comandos pelo motor ──────────────────────────────────────────────────────

def test_gradlew_e_adb_so_valem_em_projeto_android(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = motor(tmp_path)
    m.pasta = m._pasta_nova("p")
    m.plano = {"titulo": "p", "plataforma": "desktop"}
    for cmd in ("gradlew assembleDebug", "./gradlew assembleDebug", "adb devices"):
        codigo, saida = m._comando(cmd)
        assert codigo == 126 and "Android" in saida


def test_gradlew_recusa_tarefa_fora_da_lista(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = projeto_android(tmp_path)
    codigo, saida = m._comando("gradlew assembleRelease")
    assert codigo == 126 and "não é permitido" in saida


def test_gradlew_antes_do_android_preparar_orienta(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = projeto_android(tmp_path)
    codigo, saida = m._comando("gradlew assembleDebug")
    assert codigo == 127 and "android_preparar" in saida


def test_gradlew_roda_com_java_e_sdk_e_sem_a_chave_da_api(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-NAO-DEVE-VAZAR")
    m = projeto_android(tmp_path)
    assert m._executar_ferramenta("android_preparar", {}).count("ERRO") == 0
    codigo, saida = m._comando("./gradlew testDebugUnitTest assembleDebug")
    assert codigo == 0, saida
    assert "--console=plain" in saida and "chave=nenhuma" in saida and "NAO-DEVE-VAZAR" not in saida
    assert f"java={kit.jdk}" in saida and f"sdk={kit.sdk}" in saida
    assert m._apk() is not None


def test_android_preparar_nao_existe_fora_do_android(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = motor(tmp_path)
    m.pasta = m._pasta_nova("p")
    m.plano = {"plataforma": "desktop"}
    assert m._executar_ferramenta("android_preparar", {}).startswith("ERRO")


def test_android_preparar_sem_sdk_nao_finge(tmp_path, monkeypatch):
    usar_pc_vazio(monkeypatch, tmp_path)
    m = projeto_android(tmp_path)
    r = m._executar_ferramenta("android_preparar", {})
    assert r.startswith("ERRO") and "Android SDK" in r


def test_adb_pelo_motor_so_executa_o_validado(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = projeto_android(tmp_path)
    codigo, saida = m._comando("adb devices")
    assert codigo == 0 and "SER123" in saida
    codigo, saida = m._comando("adb shell rm -rf /sdcard")
    assert codigo == 126
    assert "rm" not in kit.adb_log.read_text()


# ── fluxo completo de construção ─────────────────────────────────────────────

def _fila_android():
    TF = _tf()
    resp, tu, tx = TF.resp, TF.tu, TF.tx
    plano = dict(PLANO_ANDROID)
    plano["comando_teste"] = "gradlew testDebugUnitTest assembleDebug"
    return [
        resp([tx(json.dumps(plano))], "end_turn"),                                          # arquiteto
        resp([tu("a", "escrever_arquivo", caminho="settings.gradle.kts", conteudo='rootProject.name = "oito"\n')]),
        resp([tu("b", "android_preparar")]),
        resp([tu("c", "executar_comando", comando="gradlew testDebugUnitTest assembleDebug")]),
        resp([tu("d", "concluir", resumo="App criado.", como_executar="instale o APK")]),
        resp([tu("e", "reportar_revisao", nota=8, problemas=[])]),                          # revisor
    ]


def test_construcao_android_de_ponta_a_ponta(tmp_path, monkeypatch, kit):
    TF = _tf()
    ClienteFalso = TF.ClienteFalso
    usar_kit(monkeypatch, kit)
    falas = []
    m = motor(tmp_path, falas)
    cli = ClienteFalso(_fila_android())
    m._cliente_cache = cli
    m.planejar("app android de navegação")
    assert m.construir_pendente()
    texto = " ".join(falas)
    assert "Pronto!" in texto, texto
    assert (m.pasta / "gradlew").is_file() and (m.pasta / "local.properties").is_file()
    assert m._apk() is not None
    # o construtor recebeu as regras e a ferramenta de Android; o revisor, o aviso de Android
    construtor = cli.chamadas[1]
    assert "ANDROID NATIVO" in construtor["system"] and AND.AGP_VERSAO in construtor["system"]
    assert "android_preparar" in {t["name"] for t in construtor["tools"]}
    assert "componentes exportados" in cli.chamadas[-1]["system"]
    assert "android_preparar" not in {t["name"] for t in cli.chamadas[-1]["tools"]}
    assert not cli.fila
    assert "local.properties" in (m.pasta / ".gitignore").read_text()
    # local.properties (caminho do SDK deste PC) não vai para o git
    tracked = m._git("ls-files").stdout.split()
    assert "local.properties" not in tracked and "settings.gradle.kts" in tracked


def test_projeto_comum_nao_ganha_regras_nem_ferramenta_de_android(tmp_path):
    TF = _tf()
    ClienteFalso, PLANO, fila_de_construcao = TF.ClienteFalso, TF.PLANO, TF.fila_de_construcao
    m = motor(tmp_path)
    cli = ClienteFalso(fila_de_construcao())
    m._cliente_cache = cli
    m.planejar("app de tarefas")
    assert m.construir_pendente()
    assert all("ANDROID" not in c["system"] for c in cli.chamadas)
    assert all("android_preparar" not in {t["name"] for t in c.get("tools", [])} for c in cli.chamadas)


def test_sem_android_studio_o_forge_nao_comeca_e_guarda_o_plano(tmp_path, monkeypatch):
    TF = _tf()
    ClienteFalso, resp, tx = TF.ClienteFalso, TF.resp, TF.tx
    usar_pc_vazio(monkeypatch, tmp_path)
    falas = []
    m = motor(tmp_path, falas)
    m._cliente_cache = ClienteFalso([resp([tx(json.dumps(PLANO_ANDROID))], "end_turn")])
    m.planejar("app android")
    assert m.construir_pendente() is False
    assert m.plano_pendente is not None and m.pasta is None
    assert not [d for d in (tmp_path / "raiz").iterdir() if (d / ".forge").exists()]
    assert "Android SDK" in " ".join(falas)


# ── celular e APK ────────────────────────────────────────────────────────────

def test_instala_no_unico_celular_e_abre_o_app(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    falas = []
    m = projeto_android(tmp_path)
    m.falar = falas.append
    m._executar_ferramenta("android_preparar", {})
    assert m._comando("gradlew assembleDebug")[0] == 0
    assert m.instalar_no_celular() is True
    log = kit.adb_log.read_text()
    assert "-s SER123 install -r" in log and "app-debug.apk" in log
    assert "-s SER123 shell monkey -p com.nexus.oitovias" in log
    assert "Instalei" in " ".join(falas)


def test_instalar_compila_antes_se_nao_ha_apk(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = projeto_android(tmp_path)
    m._executar_ferramenta("android_preparar", {})
    assert m._apk() is None
    assert m.instalar_no_celular() is True and m._apk() is not None


@pytest.mark.parametrize("devices,trecho", [
    ("", "Depuração USB"), ("A\tdevice\nB\tdevice\n", "mais de um aparelho"),
    ("A\tunauthorized\n", "não autorizou"), ("A\toffline\n", "Depuração USB")])
def test_instalar_explica_cada_problema_do_celular(tmp_path, monkeypatch, kit, devices, trecho):
    usar_kit(monkeypatch, kit)
    kit.devices.write_text(devices)
    falas = []
    m = projeto_android(tmp_path)
    m.falar = falas.append
    assert m.instalar_no_celular() is False
    assert trecho in " ".join(falas)
    assert "install" not in (kit.adb_log.read_text() if kit.adb_log.exists() else "")


def test_instalar_nao_vale_para_projeto_que_nao_e_android(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = motor(tmp_path)
    m.pasta, m.plano = m._pasta_nova("p"), {"plataforma": "desktop"}
    assert m.instalar_no_celular() is False


def test_entrega_do_apk_copia_para_entregas(tmp_path, monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    m = projeto_android(tmp_path)
    assert m.entregar_apk() is None
    m._executar_ferramenta("android_preparar", {})
    m._comando("gradlew assembleDebug")
    destino = m.entregar_apk()
    assert destino and destino.name == "oito-vias-debug.apk" and destino.read_text().strip() == "apk-de-mentira"
    assert destino.parent.name == "_entregas"


def test_pastas_do_gradle_nao_entram_no_zip_nem_na_listagem(tmp_path):
    m = projeto_android(tmp_path)
    (m.pasta / ".gradle").mkdir()
    (m.pasta / ".gradle" / "cache.bin").write_text("x")
    (m.pasta / "app" / "build").mkdir(parents=True)
    (m.pasta / "app" / "build" / "lixo.class").write_text("x")
    (m.pasta / "app" / "Main.kt").write_text("fun main() {}")
    listados = [p.relative_to(m.pasta).as_posix() for p in m._arquivos()]
    assert "app/Main.kt" in listados and not any(".gradle" in p or "build" in p for p in listados)


# ── ação forge_app ───────────────────────────────────────────────────────────

def test_acao_a_descricao_fala_de_android():
    d = FA.TOOL["description"]
    assert "android_check" in d and "action=install" in d and "action=apk" in d
    assert "android_check" in FA.TOOL["parameters"]["properties"]["action"]["description"]


def test_acao_android_check_resume_o_pc(monkeypatch, kit):
    usar_kit(monkeypatch, kit)
    r = FA.forge_app({"action": "android_check"})
    assert r.startswith("[done]") and "pronto" in r and "Celular conectado: 1" in r


def test_acao_android_check_pc_vazio(monkeypatch, tmp_path):
    usar_pc_vazio(monkeypatch, tmp_path)
    r = FA.forge_app({"action": "android_check"})
    assert "Falta" in r and "Android SDK" in r


def test_acao_build_android_sem_ambiente_falha_com_instrucao(monkeypatch, tmp_path):
    TF = _tf()
    ClienteFalso, resp, tx = TF.ClienteFalso, TF.resp, TF.tx
    usar_pc_vazio(monkeypatch, tmp_path)
    m = FA._motor()
    m._cliente_cache = ClienteFalso([resp([tx(json.dumps(PLANO_ANDROID))], "end_turn")])
    assert FA.forge_app({"action": "plan", "description": "app android de navegação"}).startswith("[plan]")
    r = FA.forge_app({"action": "build"})
    assert r.startswith("[failed]") and "Android Studio" in r
    assert FA._motor().plano_pendente is not None


def test_acao_build_install_e_apk_de_ponta_a_ponta(monkeypatch, kit):
    TF = _tf()
    ClienteFalso = TF.ClienteFalso
    usar_kit(monkeypatch, kit)
    m = FA._motor()
    m._cliente_cache = ClienteFalso(_fila_android())
    assert FA.forge_app({"action": "plan", "description": "app android de navegação"}).startswith("[plan]")
    r = FA.forge_app({"action": "build"})
    assert r.startswith("[done]") and "Pronto!" in r, r
    r = FA.forge_app({"action": "install"})
    assert r.startswith("[done]") and "Instalei" in r, r
    r = FA.forge_app({"action": "apk"})
    assert r.startswith("[done]") and "debug.apk" in r


def test_acao_install_em_projeto_comum_e_recusada(tmp_path):
    m = FA._motor()
    m.pasta = m._pasta_nova("p")
    m.plano = {"plataforma": "desktop"}
    assert FA.forge_app({"action": "install"}).startswith("[failed]")
    assert FA.forge_app({"action": "apk"}).startswith("[failed]")
