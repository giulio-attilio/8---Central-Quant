import os
os.environ["CENTRAL_AUTO_START_RUNTIME"] = "false"
os.environ["WERKZEUG_RUN_MAIN"] = "true"

import main
import json

def do_migration():
    print("Iniciando forca de migracao/bootstrapping...")
    try:
        result = main._trpsf_v1_apply_patch(run_bootstrap=True, force=True)
        print("Resultado da Migracao:")
        print(json.dumps(result, indent=2))
        if result.get("ok"):
            print("\nSUCESSO: Migracao concluida e estado salvo.")
        else:
            print("\nFALHA: A migracao retornou ok=False.")
    except Exception as e:
        print("Erro critico durante a migracao:", str(e))

if __name__ == "__main__":
    do_migration()
