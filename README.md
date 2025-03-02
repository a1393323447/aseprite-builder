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

# FAQ

## Windows: libcrypto-1_1-x64.dll not found
1. download [openssl-1.1.1w.zip](https://download.firedaemon.com/FireDaemon-OpenSSL/openssl-1.1.1w.zip)
2. extract `x64/bin/libcrypto-1_1-x64.dll` from `openssl-1.1.1w.zip` to the same directory as `aseprite.exe`
3. now the aseprite should working properly

