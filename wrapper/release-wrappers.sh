#!/bin/bash

for unix in patch_via_gerrit-darwin patch_via_gerrit-darwin-arm64 patch_via_gerrit-darwin-x86_64 patch_via_gerrit-linux patch_via_gerrit-linux-aarch64 patch_via_gerrit-linux-x64-musl patch_via_gerrit-linux-x86_64; do
    aws s3 cp --acl public-read patch_via_gerrit s3://packages.couchbase.com/patch_via_gerrit/$unix
done

if [ ! -e patch_via_gerrit-windows.exe ]; then
    ./make_win_wrapper.sh
fi
for win in patch_via_gerrit-windows-x86_64.exe patch_via_gerrit-windows.exe patch_via_gerrit-windows_x86_64.exe patch_via_gerrit.exe; do
    aws s3 cp --acl public-read patch_via_gerrit-windows.exe s3://packages.couchbase.com/patch_via_gerrit/$win
done
aws cloudfront create-invalidation --distribution-id E1U7LG5JV48KNP --paths '/patch_via_gerrit/*'
