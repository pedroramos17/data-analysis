# Optional Native Kernels

This directory is reserved for small ctypes kernels. The Django core does not
require C or C++ compilation. If a compiler or native library is missing, the
compute layer falls back to Python/NumPy.

Initial candidate kernels:

- rolling mean
- rolling std
- rolling zscore
- simple linear detrending
- simple correlation loops

