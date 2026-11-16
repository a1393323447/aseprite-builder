# aseprite-builder
Build Aseprite using Github action

# What should you do?
- fork this repo
- **enable workflow `Build and release Aseprite` in `Actions -- Workflows`**
- click `Action > Build and release Aseprite > run workflow` as the figure shows
  ![trigger the workflow](https://github.com/user-attachments/assets/5174f407-4daf-4e28-996e-5efb4f8751cb)
  
- now you should see the building process via `Actions` and you can find the product in `Release`

accroding to [Eula](https://github.com/aseprite/aseprite/blob/main/EULA.txt) :

> (b) Distribution.
> 
> You may not distribute copies of the SOFTWARE PRODUCT to third parties. Evaluation versions available for download from the Licensor's websites may be freely distributed.

we need to remove the product in `Releases` .

## Linux build environment

The Linux build uses `ubuntu-24.04` explicitly. The November 2026 migration of
`ubuntu-latest` to Ubuntu 26.04 exposed missing static OpenSSL dependencies in
Aseprite's bundled libarchive, causing `bsdunzip` to fail at link time. This pin
keeps the previously working baseline; it does not fix libarchive on Ubuntu 26.04.
Before packaging, the workflow runs `aseprite --version` with fresh temporary
`HOME`, `XDG_CONFIG_HOME`, and `ASEPRITE_USER_FOLDER` directories. This prevents
legacy configuration migration and home-directory resource lookups from using
the runner's files. That smoke test checks startup on the build runner, not GUI
operation or compatibility with other Linux distributions.

## macOS archives

The macOS workflows create a relocatable `aseprite` launcher and ad-hoc sign
`Aseprite.app` after resource cleanup. Before upload, they extract the ZIP into a
new path containing spaces, check the bundle signature, and run `--version`
through both the app executable and the launcher. The archive includes an
explanation of its signing status.

These builds are **not notarized or Developer ID signed**. A valid ad-hoc
signature checks bundle integrity; it does not establish Gatekeeper trust.
Gatekeeper can still block a downloaded build. Users should decide whether they
trust the source before running it. The CLI smoke tests do not test Finder/GUI
launch or compatibility with every macOS version.

For build-only validation, run the workflow with `publish=false`. The resulting
ZIP is saved as an Actions artifact instead of being uploaded to a Release.

Portable packaging and startup-check regression tests can be run with:

```sh
python3 -m unittest discover -s tests
```

These tests use command stubs; real `codesign`, `ditto`, and app startup are
checked by the corresponding platform's workflow steps.
