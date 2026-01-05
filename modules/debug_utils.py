
def log_nativos(msg):
    with open("debug_nativos.log", "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")
