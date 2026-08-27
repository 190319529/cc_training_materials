# Remote deployment

Host: `172.10.10.150:2022`

Application root: `/data/cc_training_materials`

```bash
/data/cc_training_materials/app/start.sh
/data/cc_training_materials/app/stop.sh
tail -f /data/cc_training_materials/cc_training_materials.log
```

Web address: `http://172.10.10.150:8765/`

Rebuild the Python environment without apt:

```bash
cd /data/cc_training_materials
python3 virtualenv.pyz venv
export HOME=/data/cc_training_materials/home
export PIP_CACHE_DIR=/data/cc_training_materials/pip-cache
venv/bin/python -m pip install -r app/requirements_remote_cuda124.txt
```

All application, dataset, Python environment, package cache, configuration and temporary paths are located under `/data/cc_training_materials`.
