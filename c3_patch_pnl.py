import os
import json
import shutil

DATA_DIR = "/data"
if not os.path.exists(DATA_DIR):
    DATA_DIR = "./data" # local fallback

TARGET_TRADE = "FALCON:FALCON15:BTCUSDT:SHORT"
TARGET_VAL = -1.08850668

def fix_dict(d):
    changed = False
    
    if d.get("id") == TARGET_TRADE or d.get("trade_id") == TARGET_TRADE:
        if "pnl_r" in d and d["pnl_r"] != TARGET_VAL:
            d["pnl_r"] = TARGET_VAL
            changed = True
        if "mae_r" in d and d["mae_r"] != TARGET_VAL:
            d["mae_r"] = TARGET_VAL
            changed = True
            
        if "trade" in d and isinstance(d["trade"], dict):
            if fix_dict(d["trade"]):
                changed = True
    
    for k, v in d.items():
        if k == TARGET_TRADE and isinstance(v, dict):
            if "pnl_r" in v and v["pnl_r"] != TARGET_VAL:
                v["pnl_r"] = TARGET_VAL
                changed = True
            if "mae_r" in v and v["mae_r"] != TARGET_VAL:
                v["mae_r"] = TARGET_VAL
                changed = True
                
        if isinstance(v, dict):
            if fix_dict(v):
                changed = True
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    if fix_dict(item):
                        changed = True
                        
    return changed

def patch_file(filepath):
    if not filepath.endswith('.json') and not filepath.endswith('.jsonl') and not filepath.endswith('.bak'):
        return

    try:
        # Stream mode for memory efficiency (prevents 2GB OOM)
        if filepath.endswith('.jsonl'):
            changed_any = False
            temp_path = filepath + ".tmp"
            
            with open(filepath, 'r', encoding='utf-8') as f_in, open(temp_path, 'w', encoding='utf-8') as f_out:
                for line in f_in:
                    if not line.strip():
                        f_out.write(line)
                        continue
                        
                    if TARGET_TRADE in line:
                        try:
                            obj = json.loads(line)
                            if fix_dict(obj):
                                changed_any = True
                            f_out.write(json.dumps(obj) + '\n')
                        except json.JSONDecodeError:
                            f_out.write(line)
                    else:
                        f_out.write(line)
                        
            if changed_any:
                shutil.move(temp_path, filepath)
                print(f"Patched streamed JSONL: {filepath}")
            else:
                os.remove(temp_path)
            return

        # Small file mode (registry.json)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if TARGET_TRADE not in content:
            return
            
        try:
            obj = json.loads(content)
            if isinstance(obj, dict) and fix_dict(obj):
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(obj, f, indent=4)
                print(f"Patched JSON: {filepath}")
            return
        except json.JSONDecodeError:
            pass
            
        lines = content.strip().split('\n')
        new_lines = []
        changed_any = False
        for line in lines:
            if not line.strip():
                continue
            if TARGET_TRADE in line:
                try:
                    obj = json.loads(line)
                    if fix_dict(obj):
                        changed_any = True
                    new_lines.append(json.dumps(obj))
                except json.JSONDecodeError:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        if changed_any:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines) + '\n')
            print(f"Patched file (small): {filepath}")

    except Exception as e:
        print(f"Error processing {filepath}: {e}")

def run():
    print("Starting Central Quant Data Patch (Memory Optimized)...")
    if not os.path.exists(DATA_DIR):
        print(f"Data dir {DATA_DIR} not found.")
        return
        
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            if file.endswith('.tmp'):
                continue
            patch_file(os.path.join(root, file))
    print("Patch complete.")

if __name__ == "__main__":
    run()
