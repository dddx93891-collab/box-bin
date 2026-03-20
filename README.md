# Box bin packing demo

This repository contains `packing_demo.py`, a reproducible demo that uses
[`py3dbp`](https://pypi.org/project/py3dbp/) to pack 25 differently-sized boxes
into a single bin with around 90% volume utilisation. The script also supports
rendering an animation of the packing process with Matplotlib when the
dependency is available.

## Usage

```bash
python packing_demo.py
```

The configuration at the top of the script can be tweaked to try alternative
bin sizes or item generation strategies (`tiling`, `random`, or `manual`).
Installing `py3dbp` is required to run the packing logic, and installing
`matplotlib` enables the optional animation export.