import psutil
import subprocess
import shutil

def get_system_stats():
    """
    Sistemin anlık CPU, RAM, Disk ve GPU kullanımını döndürür.
    Nvidia GPU için nvidia-smi komutu kullanılır (kurulu değilse güvenlice atlanır).
    """
    stats = {
        "cpu_percent": f"{psutil.cpu_percent(interval=None)}%",
        "ram_percent": f"{psutil.virtual_memory().percent}%",
        "disk_percent": f"{psutil.disk_usage('/').percent}%",
        "gpu_info": "GPU bulunamadı / Kullanılamıyor"
    }

    # GPU Check (NVIDIA)
    if shutil.which("nvidia-smi"):
        try:
            # Sadece GPU ismini, kullanım yüzdesini ve bellek miktarını çekmek için
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                gpu_texts = []
                for idx, line in enumerate(lines):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) == 4:
                        name, util, mem_used, mem_total = parts
                        gpu_texts.append(f"GPU {idx}: {name} | Kullanım: {util}% | VRAM: {mem_used}MB / {mem_total}MB")
                if gpu_texts:
                    stats["gpu_info"] = "\n".join(gpu_texts)
        except Exception:
            pass

    return stats
