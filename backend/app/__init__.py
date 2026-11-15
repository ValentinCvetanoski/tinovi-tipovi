import os

# Render's free plan has a fraction of one CPU. Many math-library threads
# fighting over it makes everything slower, so use one.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
