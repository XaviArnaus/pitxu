import psutil

class Memory:

    BYTES: int = 1
    KILOBYTES: int = 1024
    MEGABYTES: int = 1024 * 1024
    GIGABYTES: int = 1024 * 1024 * 1024

    def use(scale: int = None) -> float:
        if scale is None:
            scale = Memory.MEGABYTES
        
        process = psutil.Process()
        usage = process.memory_info().rss 
        # Using memory_info() to check consumption. Returns bytes.
        return float(usage / scale)
        
