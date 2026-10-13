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

Portable packaging regression tests can be run with:

```sh
python3 -m unittest discover -s tests -p 'test_package_macos.py'
```

These tests use command stubs to check packaging behavior; real `codesign`,
`ditto`, and app startup are checked by the macOS workflow itself.
