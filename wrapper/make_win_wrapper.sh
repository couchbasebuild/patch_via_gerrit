#!/bin/bash -ex

export GOOS=windows
export GOARCH=amd64

go build patch_via_gerrit-windows.go
