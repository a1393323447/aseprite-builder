# aseprite-builder
Build Aseprite using Github action

# what should I do?
- fork this repo
- choose the platform you want to build
  ```yaml
  # file: .github/workflows/build_and_release.yaml
  # ...
  # lots of codes
  # ...
  build-aseprite:
    name: Build Aseprite
    needs: create-release
    permissions:
      contents: write
    runs-on: ${{ matrix.os }}
    strategy:
        matrix:
          os: [ windows-latest, ubuntu-latest, macOS-latest ] # <------- remove platform(s) you don't want
  ```
- update `BuildLog.md` and push
- now you should see the building process via `Actions` and you can find the product in `Release`
- accroding to (Eula)[https://github.com/aseprite/aseprite/blob/main/EULA.txt] , we need to remove the product in `Release`
