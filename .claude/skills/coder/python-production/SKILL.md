---
name: python-production
description: Production-quality Python development — efficiency, multiprocessing, memory management, algorithm complexity, naming conventions, and caching. This skill should be used when writing performance-critical code, optimizing existing code, designing parallel computation, profiling bottlenecks, or reviewing code quality. Also use when the user mentions speed, slow, optimize, profile, memory, multiprocessing, vectorize, or cache.
---

# Python Production

Write fast, correct, maintainable Python. This skill covers efficiency, parallelism, memory, complexity, naming, and caching patterns specific to scientific computing with numpy/scipy and Streamlit.

## Performance Optimization

### Profiling First, Optimize Second
Never optimize without profiling. Identify the actual bottleneck:

```python
import cProfile
import pstats

# Profile a function
cProfile.run('my_function()', 'output.prof')
stats = pstats.Stats('output.prof')
stats.sort_stats('cumulative').print_stats(20)

# Line-level profiling (install: pip install line_profiler)
# Add @profile decorator, run: kernprof -l -v script.py
```

### Vectorization (numpy/scipy)
Replace Python loops with numpy operations wherever possible:

```python
# SLOW: Python loop
result = []
for i in range(len(arr)):
    result.append(arr[i] * factor + offset)

# FAST: Vectorized
result = arr * factor + offset

# SLOW: Loop over epoch pairs
for i in range(n):
    for j in range(i+1, n):
        delta_rv[i,j] = abs(rv[i] - rv[j])

# FAST: Broadcasting
delta_rv = np.abs(rv[:, None] - rv[None, :])
```

### Pre-allocation vs Append
```python
# SLOW: Append to list, convert later
results = []
for i in range(10000):
    results.append(compute(i))
result = np.array(results)

# FAST: Pre-allocate
result = np.empty(10000)
for i in range(10000):
    result[i] = compute(i)

# FASTEST: Vectorize entirely if possible
result = compute_vectorized(np.arange(10000))
```

## Multiprocessing

### Standard Pattern (this project)
```python
import multiprocessing as mp

def worker(args):
    """Pure function — no shared state, no side effects."""
    param, data = args
    return compute_result(param, data)

n_cores = os.cpu_count() - 1  # ALWAYS leave 1 core free
with mp.Pool(n_cores) as pool:
    results = pool.map(worker, task_list)
```

### Live Progress (Streamlit)
```python
progress_bar = st.progress(0)
total = len(task_list)

with mp.Pool(n_cores) as pool:
    for i, result in enumerate(pool.imap_unordered(worker, task_list)):
        results.append(result)
        progress_bar.progress((i + 1) / total)
```

### Multiprocessing Rules
- Worker functions must be **pure** — no shared mutable state
- Worker must be defined at **module level** (not nested, not lambda)
- Pass only **picklable** objects (no file handles, no Streamlit objects)
- Use `imap_unordered` when order doesn't matter (better load balancing)
- For very large data, consider `shared_memory` or memory-mapped arrays

## Memory Management

### numpy Memory Layout
```python
# C-contiguous (row-major) — default, best for row-wise operations
arr = np.array(data, order='C')

# Fortran-contiguous (column-major) — best for column-wise operations
arr = np.array(data, order='F')

# Check: arr.flags['C_CONTIGUOUS'], arr.flags['F_CONTIGUOUS']
```

### Reducing Memory Footprint
```python
# Use appropriate dtypes
arr = np.array(data, dtype=np.float32)  # Half the memory of float64

# Delete large intermediates
del large_temporary_array
import gc; gc.collect()

# Memory-mapped files for very large arrays
arr = np.load('large_file.npy', mmap_mode='r')
```

## Algorithm Complexity

### When It Matters
- N < 1000: Almost anything is fine
- N = 10,000: O(n²) starts to hurt (~100M operations)
- N = 100,000+: Must be O(n log n) or better

### Common Patterns in This Project
| Operation | Naive | Optimized |
|-----------|-------|-----------|
| All epoch pairs | O(n²) nested loop | O(n²) but vectorized (unavoidable) |
| Grid search | O(grid_size × n_stars × n_epochs) | Parallelize over grid points |
| CDF comparison | Sort + compare | `np.searchsorted` for quantiles |
| Find max ΔRV | O(n²) pairs | O(n) with argmin/argmax first |

## Caching Patterns

### Streamlit Caching
```python
@st.cache_data  # Cache return value based on args
def load_data(star_name):
    return expensive_computation(star_name)

# IMPORTANT: _prefixed params excluded from cache key
@st.cache_data
def compute(_star_object, param):  # _star_object not hashed
    return _star_object.process(param)
```

### functools Caching
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_pure_function(hashable_arg):
    return compute(hashable_arg)
```

## Naming Conventions

### Variables and Functions
- `snake_case` for variables and functions
- `UPPER_CASE` for constants
- Descriptive names: `delta_rv_max` not `d`, `epoch_count` not `n`
- Boolean variables: `is_binary`, `has_data`, `should_filter`
- Functions: verb-first: `load_observations()`, `compute_ccf()`, `filter_epochs()`

### Module Organization
- One module = one responsibility
- Keep files under 300 lines (prefer splitting early)
- Imports at top, constants after imports, functions/classes after
- Public API first, private helpers (prefixed `_`) after

## Code Quality Checklist
- [ ] Profiled before optimizing
- [ ] numpy operations vectorized where possible
- [ ] Arrays pre-allocated (no append loops for large N)
- [ ] Multiprocessing workers are pure functions at module level
- [ ] Appropriate dtypes (float32 vs float64)
- [ ] `@st.cache_data` on expensive computations
- [ ] Descriptive variable names
- [ ] Functions under 50 lines (extract helpers if longer)
