# Multifractal Features

The finance feature layer provides lightweight log-return, realized-volatility, MF-DFA, MF-DMA, Haar wavelet, roughness, spectrum-width, intermittency, and joint-correlation baselines. PyWavelets is used only when installed; otherwise the Haar fallback keeps the feature path dependency-light.

EMD/IMF extraction is behind `FIN_MULTIFRACTAL_EMD=false` by default. PyEMD is not a mandatory dependency. WTMM and wavelet-leader interfaces are placeholders until a validated implementation is added.
