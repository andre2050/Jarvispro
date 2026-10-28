"""Ferramenta para QUEM CRIA plugins: gera chaves, empacota e assina um .nexusplugin.

    python ferramentas/assinar_plugin.py gerar-chave  meu_nome
    python ferramentas/assinar_plugin.py empacotar    pasta_com_os_py  --id meu_plugin --nome "Meu Plugin" \
                                                       --versao 1.0 --autor "Meu Nome" --descricao "O que faz" \
                                                       --chave meu_nome.privada
Guarde o arquivo .privada em lugar seguro e NUNCA o compartilhe; quem usa o plugin recebe só a chave pública."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import plugin_loja as L  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar-chave")
    g.add_argument("nome")
    e = sub.add_parser("empacotar")
    e.add_argument("pasta")
    for k in ("id", "nome", "versao", "autor", "descricao"):
        e.add_argument("--" + k, required=True)
    e.add_argument("--chave", help="arquivo .privada para assinar (sem ele o pacote sai sem assinatura)")
    e.add_argument("--saida", help="caminho do .nexusplugin (padrão: <id>.nexusplugin)")
    a = ap.parse_args()
    if a.cmd == "gerar-chave":
        priv, pub = L.gerar_par_de_chaves()
        Path(f"{a.nome}.privada").write_text(priv, encoding="utf-8")
        Path(f"{a.nome}.publica").write_text(pub, encoding="utf-8")
        print(f"Criados {a.nome}.privada (SEGREDO) e {a.nome}.publica (pode divulgar).")
        return 0
    chave = Path(a.chave).read_text(encoding="utf-8").strip() if a.chave else None
    try:
        out = L.empacotar(a.pasta, a.saida or f"{a.id}.nexusplugin",
                          {"id": a.id, "nome": a.nome, "versao": a.versao, "autor": a.autor, "descricao": a.descricao}, chave)
    except L.ErroPacote as ex:
        print("Erro:", ex)
        return 1
    print("Pacote criado:", out, "(assinado)" if chave else "(SEM assinatura)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
