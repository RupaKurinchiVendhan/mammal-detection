#!/usr/bin/env python3
"""Read a remote ZIP's directory over HTTP without downloading the archive.

zipfile only needs random access, so a file-like object backed by HTTP Range
requests lets us list a 60 GB archive's members - names, counts, uncompressed
sizes - for a few kilobytes of traffic, and pull individual small members out of
it. Servers that ignore Range are detected and reported rather than silently
returning the whole body.
"""
import io, os, urllib.request

UA = {"User-Agent": "bioacoustic-catalogue/1.0 (dataset audit)"}


class HttpFile(io.RawIOBase):
    def __init__(self, url, timeout=60):
        self.url = url
        self.timeout = timeout
        self._pos = 0
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            self.size = int(r.headers["Content-Length"])
            self.ranged = r.headers.get("Accept-Ranges", "") == "bytes"

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self._pos

    def seek(self, off, whence=0):
        self._pos = (off if whence == 0 else
                     self._pos + off if whence == 1 else self.size + off)
        return self._pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self._pos
        if n == 0 or self._pos >= self.size:
            return b""
        end = min(self._pos + n, self.size) - 1
        req = urllib.request.Request(
            self.url, headers={**UA, "Range": f"bytes={self._pos}-{end}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            if r.status != 206:
                raise OSError(f"server ignored Range (status {r.status})")
            data = r.read()
        self._pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def zenodo_link(rec, key, meta=None):
    """Zenodo's per-file download URL; content.hosts redirect, which urllib follows."""
    import json
    if meta is None:
        with urllib.request.urlopen(
                urllib.request.Request(f"https://zenodo.org/api/records/{rec}",
                                       headers=UA), timeout=60) as r:
            meta = json.load(r)
    for f in meta.get("files", []):
        if f["key"] == key:
            return f["links"]["self"]
    raise KeyError(f"{key} not in record {rec}")
