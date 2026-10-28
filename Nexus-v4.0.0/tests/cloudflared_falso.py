"""cloudflared de mentira para os testes: imprime a URL do túnel e fica vivo. Não é um teste em si."""
import sys
import time

print("2026-10-28 INF Thank you for trying Cloudflare Tunnel", flush=True)
print("2026-10-28 INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
if "--sem-url" in sys.argv:
    time.sleep(30)
print("2026-10-28 INF |  https://exemplo-teste-123.trycloudflare.com  |", flush=True)
print("ARGS:" + " ".join(sys.argv[1:]), flush=True)
time.sleep(60)
