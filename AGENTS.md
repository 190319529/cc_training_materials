# cc_training_materials agent notes

## Scope

- Application entry point: `cc_training_materials.py`
- Browser UI: `cc_training_materials_web/index.html`, `app.js`, `styles.css`
- Local launcher: `start_cc_training_materials.sh`
- Image de-duplication utility: `image_similarity_dedup.py`

## Working rules

- Keep images, YOLO labels, model weights, `runs/`, logs, caches and virtual environments outside Git.
- Preserve the existing two-class mapping unless the user explicitly changes it: `0` drone, `1` bird.
- Validate Python changes with `python3 -m py_compile cc_training_materials.py`.
- Validate frontend JavaScript with `node --check cc_training_materials_web/app.js`.
- Do not edit the production copy directly. Deploy the application to `/data/cc_training_materials/app/` only after local changes are checked.
- The production service listens on `0.0.0.0:8765`.

## Data safety

- Saving labels changes the dataset on disk; deleting images must remain recoverable through the application's trash flow.
- Never commit credentials, local SSH helpers, datasets, `.pt` files or generated training results.
