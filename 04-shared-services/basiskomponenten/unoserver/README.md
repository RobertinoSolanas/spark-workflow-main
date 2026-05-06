# Unoserver

A containerized document format conversion service based on LibreOffice and [unoserver](https://github.com/unoconv/unoserver-docker). Converts documents between formats (e.g. DOCX → PDF) via the UNO protocol.

## Overview

The *Unoserver* is responsible for:

- **Document conversion**: Converting files between office formats using LibreOffice
- **Font support**: Providing a comprehensive set of fonts (Noto, DejaVu, Liberation) for accurate rendering
- **Network access**: Exposing the UNO conversion interface on port 2003

## Configuration

| Variable              | Description                           | Default |
| --------------------- | ------------------------------------- | ------- |
| `CONVERSION_TIMEOUT`  | Timeout for each conversion (seconds) | `120`   |

## Docker

```bash
docker build -t unoserver .
docker run -p 2003:2003 -v ./data:/data unoserver
```

The service will be available at port **2003** (UNO protocol).

### Adjusting the Timeout

```bash
docker run -p 2003:2003 -e CONVERSION_TIMEOUT=300 unoserver
```

## Usage

Use the `unoconvert` CLI or any UNO-compatible client to send conversion requests:

```bash
unoconvert --host-location remote --host <host> --port 2003 input.docx output.pdf
```
