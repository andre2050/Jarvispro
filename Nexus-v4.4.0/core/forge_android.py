# -*- coding: utf-8 -*-
"""
Módulo Android do Forge (NEXUS 4.3).

Acha o JDK, o Android SDK, o adb e o Gradle deste PC, prepara o projeto (local.properties, gradle.properties,
gradlew) e fala com o celular por adb — sempre com listas fechadas do que pode ser rodado. Só gera APK de
DEPURAÇÃO (debug): assinar release para a Play Store fica de fora.

Sem tela e sem voz: quem usa é core/forge_engine.py. Tudo recebe `env`/`home` para poder ser testado com pastas
de mentira.

Honesto: o app e o build.gradle que a IA escreve são código que roda no seu PC (o Gradle executa o script do
projeto). As listas abaixo limitam o que a IA consegue pedir ao Forge, não o que o script do projeto faz.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

# Conjunto de versões que funcionam juntas (o construtor é instruído a usá-las).
JDK_MINIMO = 17
GRADLE_VERSAO = "8.9"
AGP_VERSAO = "8.5.2"
KOTLIN_VERSAO = "2.0.20"
COMPILE_SDK = 34
MIN_SDK = 26
COMPOSE_BOM = "2024.09.00"

WIN = os.name == "nt"
APK_PADRAO = "app/build/outputs/apk/debug/app-debug.apk"

MSG_SEM_GRADLE = ("um Gradle para gerar o gradlew (abra qualquer projeto no Android Studio uma vez, "
                  "que ele baixa o Gradle, ou instale o Gradle)")

SISTEMA_ANDROID = f"""Este é um projeto ANDROID NATIVO (Kotlin + Jetpack Compose). Siga:
- Versões fixas, conhecidas por funcionar juntas: Gradle {GRADLE_VERSAO}, Android Gradle Plugin {AGP_VERSAO}, Kotlin {KOTLIN_VERSAO} com o plugin org.jetbrains.kotlin.plugin.compose, compileSdk {COMPILE_SDK}, targetSdk {COMPILE_SDK}, minSdk {MIN_SDK}, JDK {JDK_MINIMO}, Compose BOM {COMPOSE_BOM}. Só mude uma versão se o erro do build pedir.
- Estrutura: settings.gradle.kts, build.gradle.kts (raiz), app/build.gradle.kts, app/src/main/AndroidManifest.xml, app/src/main/java/<pacote>/MainActivity.kt, app/src/main/res/ (strings e tema) e testes em app/src/test/java. Use kotlin DSL (.kts) e AndroidX.
- applicationId e namespace = o "pacote" do plano. Texto da interface em português do Brasil.
- NÃO crie gradle.properties, local.properties nem gradlew: a ferramenta android_preparar cria. Depois de escrever settings.gradle.kts e os build.gradle.kts, chame android_preparar e só então use executar_comando com gradlew.
- Comandos permitidos: gradlew assembleDebug | testDebugUnitTest | lintDebug | clean (com --stacktrace se precisar), e adb: devices, install -r <apk>, logcat -d, shell am start -n pacote/.Atividade, shell monkey -p pacote -c android.intent.category.LAUNCHER 1.
- Escreva testes unitários (JUnit) para a lógica que não depende do Android (cálculos, formatação, regras) e rode gradlew testDebugUnitTest assembleDebug até passar.
- Peça no manifesto só as permissões necessárias; localização em segundo plano só se o app realmente precisar.
- Apps de navegação: use componentes de código aberto para mapa e rota (por exemplo MapLibre ou osmdroid, e um motor de rotas como OSRM, GraphHopper ou Valhalla) e o TextToSpeech do Android para a voz; respeite a licença e a atribuição dos dados do OpenStreetMap.
- Escreva o código do zero: não copie nomes, código nem arquivos de outros aplicativos."""

SISTEMA_REVISOR_ANDROID = ("Em projetos Android, olhe também: permissões do manifesto a mais, localização em segundo plano "
                           "sem necessidade, componentes exportados sem proteção, segredos no código, uso de rede sem HTTPS.")

TAREFAS_GRADLE = re.compile(r"^(?::[A-Za-z0-9_-]+:)?(assembleDebug|testDebugUnitTest|lintDebug|clean)$")
FLAGS_GRADLE = {"--stacktrace", "--info", "--warning-mode=summary", "--warning-mode=all", "--warning-mode=none",
                "--no-daemon", "--offline", "-q", "--quiet", "--console=plain", "--rerun-tasks", "--continue"}
FILTRO_LOGCAT = re.compile(r"^[A-Za-z0-9_.*]+:[VDIWEFS]$")
SERIAL = re.compile(r"^[A-Za-z0-9._:\-]+$")
ATIVIDADE = re.compile(r"^[A-Za-z_][\w.]*/[.\w$]+$")
PACOTE = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)+$")


# ── achar as ferramentas ─────────────────────────────────────────────────────

def _exe(nome: str) -> str:
    return nome + (".exe" if WIN else "")


def _caminho(env: Mapping[str, str]) -> str:
    return env.get("PATH", "")


def achar_sdk(env: Optional[Mapping[str, str]] = None, home: Optional[Path] = None) -> Optional[Path]:
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = env.get(var)
        if v and Path(v).is_dir():
            return Path(v)
    locais = []
    if env.get("LOCALAPPDATA"):
        locais.append(Path(env["LOCALAPPDATA"]) / "Android" / "Sdk")
    locais += [home / "AppData" / "Local" / "Android" / "Sdk", home / "Library" / "Android" / "sdk",
               home / "Android" / "Sdk"]
    return next((c for c in locais if c.is_dir()), None)


def parse_versao_java(texto: str) -> Optional[int]:
    """'openjdk version "17.0.9"' -> 17;  '"1.8.0_392"' -> 8;  '"21"' -> 21."""
    m = re.search(r'version "(\d+)(?:\.(\d+))?', texto or "")
    if not m:
        return None
    maior = int(m.group(1))
    return int(m.group(2) or 0) if maior == 1 else maior


def versao_java(exe: Path, env: Optional[Mapping[str, str]] = None) -> Optional[int]:
    try:
        r = subprocess.run([str(exe), "-version"], capture_output=True, text=True, timeout=20, env=dict(env) if env else None)
        return parse_versao_java((r.stderr or "") + (r.stdout or ""))
    except Exception:
        return None


def achar_java(env: Optional[Mapping[str, str]] = None, home: Optional[Path] = None):
    """Devolve (java_home, java_exe, versão). Prefere um JDK >= 17 (o JDK embutido no Android Studio serve)."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    homes: list[Path] = []
    if env.get("JAVA_HOME"):
        homes.append(Path(env["JAVA_HOME"]))
    for var in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA"):
        if env.get(var):
            base = Path(env[var])
            homes += [base / "Android" / "Android Studio" / "jbr", base / "Programs" / "Android Studio" / "jbr"]
    homes += [Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home"), Path("/opt/android-studio/jbr"),
              Path("/usr/local/android-studio/jbr"), home / "android-studio" / "jbr"]
    achados = [(h, h / "bin" / _exe("java")) for h in homes if (h / "bin" / _exe("java")).is_file()]
    no_path = shutil.which("java", path=_caminho(env))
    if no_path:
        p = Path(no_path).resolve()
        achados.append((p.parent.parent, p))
    candidatos = [(h, e, versao_java(e, env)) for h, e in achados]
    for h, e, v in candidatos:
        if v is not None and v >= JDK_MINIMO:
            return h, e, v
    return candidatos[0] if candidatos else (None, None, None)


def achar_adb(sdk: Optional[Path], env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    env = os.environ if env is None else env
    if sdk and (sdk / "platform-tools" / _exe("adb")).is_file():
        return sdk / "platform-tools" / _exe("adb")
    w = shutil.which("adb", path=_caminho(env))
    return Path(w) if w else None


def _chave_versao(p: Path):
    m = re.search(r"gradle-(\d+(?:\.\d+)*)", str(p))
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def achar_gradle(env: Optional[Mapping[str, str]] = None, home: Optional[Path] = None) -> Optional[Path]:
    """Qualquer Gradle serve: só é usado para gerar o gradlew (o resto roda pelo gradlew do projeto)."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    w = shutil.which("gradle", path=_caminho(env))
    if w:
        return Path(w)
    dists = home / ".gradle" / "wrapper" / "dists"
    achados = [p for p in dists.glob("gradle-*/*/gradle-*/bin/gradle" + (".bat" if WIN else "")) if p.is_file()] \
        if dists.is_dir() else []
    return max(achados, key=_chave_versao) if achados else None


@dataclass
class Toolchain:
    sdk: Optional[Path] = None
    java_home: Optional[Path] = None
    java_exe: Optional[Path] = None
    java_versao: Optional[int] = None
    adb: Optional[Path] = None
    gradle: Optional[Path] = None
    licencas: bool = False
    plataforma: bool = False
    base: list = field(default_factory=list)       # o que falta para compilar (SDK, licenças, JDK)
    avisos: list = field(default_factory=list)

    def faltando_para(self, pasta: Optional[Path] = None) -> list:
        """O que falta. Com `pasta` de um projeto que já tem gradlew, o Gradle solto não é necessário."""
        falta = list(self.base)
        tem_wrapper = bool(pasta and (Path(pasta) / ("gradlew.bat" if WIN else "gradlew")).is_file())
        if not self.gradle and not tem_wrapper:
            falta.append(MSG_SEM_GRADLE)
        return falta

    @property
    def ok(self) -> bool:
        return not self.faltando_para(None)


def detectar(env: Optional[Mapping[str, str]] = None, home: Optional[Path] = None) -> Toolchain:
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    sdk = achar_sdk(env, home)
    java_home, java_exe, java_v = achar_java(env, home)
    tc = Toolchain(sdk=sdk, java_home=java_home, java_exe=java_exe, java_versao=java_v,
                   adb=achar_adb(sdk, env), gradle=achar_gradle(env, home))
    tc.licencas = bool(sdk and (sdk / "licenses" / "android-sdk-license").is_file())
    tc.plataforma = bool(sdk and any((sdk / "platforms" / f"android-{n}").is_dir()
                                     for n in range(COMPILE_SDK, COMPILE_SDK + 12)))
    if not sdk:
        tc.base.append("o Android SDK (instale o Android Studio e abra-o uma vez para ele baixar o SDK)")
    elif not tc.licencas:
        tc.base.append("aceitar as licenças do Android SDK (no Android Studio: SDK Manager; ou rode sdkmanager --licenses)")
    if not java_exe:
        tc.base.append(f"o JDK {JDK_MINIMO} ou mais novo (o Android Studio já traz um; defina JAVA_HOME ou instale o JDK)")
    elif (java_v or 0) < JDK_MINIMO:
        tc.base.append(f"um JDK mais novo: o que achei é o {java_v or '?'} e o Android precisa do {JDK_MINIMO} ou mais")
    if sdk and tc.licencas and not tc.plataforma:
        tc.avisos.append(f"a plataforma Android {COMPILE_SDK} será baixada no primeiro build (demora um pouco)")
    if not tc.adb:
        tc.avisos.append("sem o adb (platform-tools) não consigo instalar no celular")
    return tc


def resumo(tc: Toolchain, pasta: Optional[Path] = None) -> str:
    falta = tc.faltando_para(pasta)
    if falta:
        return "Falta no ambiente Android deste PC: " + "; ".join(falta) + "."
    extra = (" Avisos: " + "; ".join(tc.avisos) + ".") if tc.avisos else ""
    return f"Ambiente Android pronto: JDK {tc.java_versao}, SDK, Gradle e adb achados.{extra}"


def ambiente(tc: Toolchain, base: Mapping[str, str]) -> dict:
    """O ambiente do processo filho: JAVA_HOME, ANDROID_HOME e o PATH com java e adb."""
    env = dict(base)
    extra = []
    if tc.java_home:
        env["JAVA_HOME"] = str(tc.java_home)
        extra.append(str(tc.java_home / "bin"))
    if tc.sdk:
        env["ANDROID_HOME"] = env["ANDROID_SDK_ROOT"] = str(tc.sdk)
    if tc.adb:
        extra.append(str(tc.adb.parent))
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


def listar_dispositivos(adb: Path, env: Optional[Mapping[str, str]] = None, timeout: int = 20) -> list:
    """[(serial, estado)] — estado: device | unauthorized | offline."""
    r = subprocess.run([str(adb), "devices"], capture_output=True, text=True, timeout=timeout,
                       env=dict(env) if env else None)
    saida = []
    for linha in (r.stdout or "").splitlines()[1:]:
        p = linha.split()
        if len(p) >= 2:
            saida.append((p[0], p[1]))
    return saida


# ── preparar o projeto ───────────────────────────────────────────────────────

def gerar_wrapper(pasta: Path, tc: Toolchain, env: Mapping[str, str]):
    """Cria gradlew/gradlew.bat/gradle-wrapper.jar rodando `gradle wrapper` numa pasta vazia (não depende do
    build do projeto, que pode estar quebrado). Devolve (ok, mensagem)."""
    pasta = Path(pasta)
    alvo = pasta / ("gradlew.bat" if WIN else "gradlew")
    if alvo.is_file():
        return True, "O gradlew já existe."
    if not tc.gradle:
        return False, "Não consegui gerar o gradlew: falta " + MSG_SEM_GRADLE + "."
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "settings.gradle").write_text("", encoding="utf-8")
        r = subprocess.run([str(tc.gradle), "wrapper", "--gradle-version", GRADLE_VERSAO, "--console=plain"],
                           cwd=tmp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=300, env=dict(env), stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return False, "O Gradle não conseguiu gerar o gradlew: " + ((r.stderr or r.stdout or "")[-400:]).strip()
        for rel in ("gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties"):
            origem = Path(tmp) / rel
            if origem.is_file():
                destino = pasta / rel
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origem, destino)
    if not alvo.is_file():
        return False, "O Gradle terminou, mas não criou o gradlew."
    try:
        (pasta / "gradlew").chmod(0o755)
    except OSError:
        pass
    return True, f"gradlew criado (Gradle {GRADLE_VERSAO})."


def preparar_projeto(pasta: Path, tc: Toolchain, env: Mapping[str, str]) -> list:
    """local.properties (sdk.dir), gradle.properties, .gitignore e o gradlew. Devolve linhas de relatório."""
    pasta = Path(pasta)
    msgs = []
    if tc.sdk:
        (pasta / "local.properties").write_text(f"sdk.dir={tc.sdk.as_posix()}\n", encoding="utf-8")
        msgs.append("local.properties criado com o caminho do SDK.")
    gp = pasta / "gradle.properties"
    if not gp.exists():
        gp.write_text("org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n"
                      "kotlin.code.style=official\nandroid.nonTransitiveRClass=true\n", encoding="utf-8")
        msgs.append("gradle.properties criado.")
    gi = pasta / ".gitignore"
    atual = gi.read_text(encoding="utf-8") if gi.exists() else ""
    faltam = [x for x in ("local.properties", ".gradle/", "build/", ".idea/", "*.apk") if x not in atual.split()]
    if faltam:
        gi.write_text(atual.rstrip("\n") + "\n" + "\n".join(faltam) + "\n", encoding="utf-8")
    ok, m = gerar_wrapper(pasta, tc, env)
    msgs.append(("" if ok else "ERRO: ") + m)
    return msgs


# ── listas fechadas de comandos ──────────────────────────────────────────────

def validar_gradle(args) -> Optional[str]:
    """None se o gradlew pode rodar com estes argumentos; senão a frase do erro."""
    tarefas = 0
    for a in args:
        if a in FLAGS_GRADLE:
            continue
        if TAREFAS_GRADLE.match(a):
            tarefas += 1
            continue
        return (f"'{a}' não é permitido no gradlew. Tarefas: assembleDebug, testDebugUnitTest, lintDebug, clean; "
                f"opções: {', '.join(sorted(FLAGS_GRADLE))}.")
    return None if tarefas else "Diga ao gradlew uma tarefa: assembleDebug, testDebugUnitTest, lintDebug ou clean."


def validar_adb(args, pasta: Path, pacote: str = ""):
    """Devolve a lista de argumentos do adb já validada (o APK vira caminho absoluto). Levanta ValueError."""
    a = list(args)
    pre: list = []
    if len(a) >= 2 and a[0] == "-s":
        if not SERIAL.match(a[1]):
            raise ValueError("número de série do aparelho inválido")
        pre, a = ["-s", a[1]], a[2:]
    if not a:
        raise ValueError("diga ao adb o que fazer: devices, install, logcat -d, shell am start ou monkey")
    sub, resto = a[0], a[1:]
    if sub == "devices":
        if resto not in ([], ["-l"]):
            raise ValueError("adb devices só aceita -l")
    elif sub == "install":
        flags = [x for x in resto if x.startswith("-")]
        arqs = [x for x in resto if not x.startswith("-")]
        if any(f not in ("-r", "-d", "-t") for f in flags) or len(arqs) != 1 or not arqs[0].lower().endswith(".apk"):
            raise ValueError("adb install aceita só -r, -d, -t e um arquivo .apk do projeto")
        base = Path(pasta).resolve()
        apk = (base / arqs[0]).resolve()
        if base not in apk.parents:
            raise ValueError("o APK precisa estar dentro da pasta do projeto")
        if not apk.is_file():
            raise ValueError("esse APK não existe; compile primeiro (gradlew assembleDebug)")
        resto = flags + [str(apk)]
    elif sub == "uninstall":
        if len(resto) != 1 or not pacote or resto[0] != pacote:
            raise ValueError("adb uninstall só vale para o pacote deste projeto")
    elif sub == "logcat":
        if "-d" not in resto:
            raise ValueError("adb logcat precisa do -d (lê o que já está no registro e termina)")
        i = 0
        while i < len(resto):
            t = resto[i]
            if t == "-d":
                i += 1
            elif t == "-t" and i + 1 < len(resto) and resto[i + 1].isdigit():
                i += 2
            elif t == "-v" and i + 1 < len(resto) and resto[i + 1] in ("brief", "time", "threadtime"):
                i += 2
            elif FILTRO_LOGCAT.match(t):
                i += 1
            else:
                raise ValueError(f"'{t}' não é permitido no adb logcat")
    elif sub == "shell":
        ok = (len(resto) == 4 and resto[:2] == ["am", "start"] and resto[2] == "-n" and ATIVIDADE.match(resto[3])) \
            or (len(resto) == 6 and resto[0] == "monkey" and resto[1] == "-p" and PACOTE.match(resto[2])
                and resto[3:] == ["-c", "android.intent.category.LAUNCHER", "1"]) \
            or (len(resto) == 3 and resto[:2] == ["am", "force-stop"] and PACOTE.match(resto[2])) \
            or resto == ["pm", "list", "packages"]
        if not ok:
            raise ValueError("adb shell só aceita: am start -n pacote/.Atividade, monkey -p pacote ... 1, "
                             "am force-stop pacote e pm list packages")
    else:
        raise ValueError(f"adb {sub} não é permitido")
    return pre + [sub] + resto


def pacote_padrao(titulo: str) -> str:
    """applicationId válido a partir do título: com.nexus.<slug>."""
    import unicodedata
    t = unicodedata.normalize("NFKD", titulo.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "", t) or "app"
    if not slug[0].isalpha():
        slug = "app" + slug
    return f"com.nexus.{slug[:30]}"
