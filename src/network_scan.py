import subprocess
import requests

def is_reachable(ip):
    # Einfache Ping-Funktion, benötigt evtl. root-Rechte oder spezielle Optionen
    # Alternativ kann man versuchen, die API direkt per requests aufzurufen
    # Hier nur ein Ping-Beispiel:
    result = subprocess.run(['ping', '-c', '1', '-W', '1', ip], stdout=subprocess.DEVNULL)
    return result.returncode == 0

def find_first_switch(base, start, end):
    """
    Durchsucht den angegebenen IP-Bereich nach einem erreichbaren Switch.
    Angenommen, dass die Switch-API auf https://IP:8443/api/v1 oder ähnlich läuft.
    """
    for i in range(start, end+1):
        candidate = f"{base}.{i}"
        # Beispiel: Prüfung per HEAD-Request auf /login Endpoint
        try:
            url = f"https://{candidate}:8443/api/v1/login"
            resp = requests.head(url, timeout=1, verify=False)  # verify=False nur wenn kein korrektes SSL-Zertifikat
            if resp.status_code in [200, 401, 403]:  # Irgendeine erwartbare Antwort
                return candidate
        except:
            pass
    return None
