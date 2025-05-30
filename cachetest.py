import timeit
import random
import string
import tempfile
from shared import g_cm, DiskCacheWrapper

g_cs = DiskCacheWrapper("tempfile.gettempdir()")

# --- Test Configuration ---
NUM_ELEMENTS = 30
VALUE_SIZE = 1024  # Size of the value to store in bytes
NUM_RUNS = 1000    # Number of times to repeat the read/write operations for timing

# --- Test Data Generation ---
def generate_random_string(size):
    """Generates a random string of a given size."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

test_keys = [f"test_key_{i}" for i in range(NUM_ELEMENTS)]
test_values = [generate_random_string(VALUE_SIZE) for _ in range(NUM_ELEMENTS)]
test_data = dict(zip(test_keys, test_values))

# --- Helper Functions ---
def clear_caches():
    """Clears both g_cs and g_cm."""
    print("Clearing caches...")
    # Clear diskcache (g_cs) - Note: clear() removes all items
    g_cs.cache.clear()
    # Clear cacheout (g_cm)
    g_cm.clear()
    print("Caches cleared.")

def setup_g_cs():
    """Pre-populate g_cs for read tests."""
    g_cs.cache.clear() # Ensure clean state
    for key, value in test_data.items():
        g_cs.put(key, value)

def setup_g_cm():
    """Pre-populate g_cm for read tests."""
    g_cm.clear() # Ensure clean state
    for key, value in test_data.items():
        g_cm.set(key, value) # Use set for cacheout

# --- Test Functions ---
def test_write_g_cs():
    """Tests writing NUM_ELEMENTS to g_cs."""
    for key, value in test_data.items():
        g_cs.put(key, value)

def test_read_g_cs():
    """Tests reading NUM_ELEMENTS from g_cs."""
    for key in test_keys:
        g_cs.get(key)

def test_write_g_cm():
    """Tests writing NUM_ELEMENTS to g_cm."""
    for key, value in test_data.items():
        g_cm.set(key, value) # Use set for cacheout

def test_read_g_cm():
    """Tests reading NUM_ELEMENTS from g_cm."""
    for key in test_keys:
        g_cm.get(key)

# --- Benchmarking ---
if __name__ == "__main__":
    print("--- Cache Performance Benchmark ---") # Removed unnecessary f-string
    print(f"Number of elements: {NUM_ELEMENTS}")
    print(f"Value size: {VALUE_SIZE} bytes")
    print(f"Number of runs per test: {NUM_RUNS}")
    print("-" * 30)

    # --- g_cs (diskcache) Benchmarks ---
    print("Benchmarking g_cs (diskcache)...")
    # Write Test
    clear_caches() # Clear before write test
    g_cs_write_time = timeit.timeit(test_write_g_cs, number=NUM_RUNS)
    print(f"g_cs Write Time ({NUM_RUNS} runs): {g_cs_write_time:.6f} seconds")
    avg_write_g_cs = (g_cs_write_time / NUM_RUNS) / NUM_ELEMENTS
    print(f"   Avg time per write op: {avg_write_g_cs * 1e6:.4f} microseconds")


    # Read Test (ensure data is present)
    setup_g_cs() # Pre-populate for read test
    g_cs_read_time = timeit.timeit(test_read_g_cs, number=NUM_RUNS)
    print(f"g_cs Read Time ({NUM_RUNS} runs):  {g_cs_read_time:.6f} seconds")
    avg_read_g_cs = (g_cs_read_time / NUM_RUNS) / NUM_ELEMENTS
    print(f"   Avg time per read op:  {avg_read_g_cs * 1e6:.4f} microseconds")
    print("-" * 30)


    # --- g_cm (cacheout) Benchmarks ---
    print("Benchmarking g_cm (cacheout - in-memory)...")
    # Write Test
    clear_caches() # Clear before write test
    g_cm_write_time = timeit.timeit(test_write_g_cm, number=NUM_RUNS)
    print(f"g_cm Write Time ({NUM_RUNS} runs): {g_cm_write_time:.6f} seconds")
    avg_write_g_cm = (g_cm_write_time / NUM_RUNS) / NUM_ELEMENTS
    print(f"   Avg time per write op: {avg_write_g_cm * 1e6:.4f} microseconds")


    # Read Test (ensure data is present)
    setup_g_cm() # Pre-populate for read test
    g_cm_read_time = timeit.timeit(test_read_g_cm, number=NUM_RUNS)
    print(f"g_cm Read Time ({NUM_RUNS} runs):  {g_cm_read_time:.6f} seconds")
    avg_read_g_cm = (g_cm_read_time / NUM_RUNS) / NUM_ELEMENTS
    print(f"   Avg time per read op:  {avg_read_g_cm * 1e6:.4f} microseconds")
    print("-" * 30)

    # --- Comparison ---
    print("--- Comparison ---")
    try:
        write_factor = avg_write_g_cs / avg_write_g_cm
        print(f"Write: g_cs is {write_factor:.2f}x slower than g_cm")
    except ZeroDivisionError:
        print("Write: g_cm was too fast to measure reliably for comparison.") # Fixed indentation

    try:
        read_factor = avg_read_g_cs / avg_read_g_cm
        print(f"Read:  g_cs is {read_factor:.2f}x slower than g_cm")
    except ZeroDivisionError:
        print("Read: g_cm was too fast to measure reliably for comparison.")

    print("-" * 30)
    print("Benchmark complete.")

