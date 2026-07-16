# QuantVolt documentation site

Static, dependency-free documentation generated from the QuantVolt source tree.

## Preview

From the repository root:

```bash
python3 -m http.server 8000 --directory site
```

Open <http://127.0.0.1:8000/>. Directly opening `index.html` also works, but an HTTP preview
matches production hosting more closely.

## Regenerate the API reference

After changing public exports, signatures, or docstrings:

```bash
python3 site/build_api.py
```

The generator reads every public subpackage's `__all__`, resolves re-exports, and writes
`api-data.js`. It does not import QuantVolt, so native/runtime dependencies are not required
to build the documentation.

Authored tutorials and their example outputs live in `content.js`. The documentation shell,
router, search, and theme behavior live in `script.js`.
