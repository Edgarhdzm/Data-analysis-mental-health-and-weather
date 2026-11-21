"""Acceso de solo lectura al repositorio abierto de Open-Meteo (Amazon S3) por HTTP.

La libreria omfiles pide miles de trocitos de ~4 KB. Si cada uno fuera una peticion
de red, leer un estado tardaria minutos. Esta clase baja bloques grandes alineados
(1 MB por defecto), los guarda en memoria y sirve los trocitos desde ahi.

Si se corta internet, reintenta durante unos 20 minutos antes de rendirse.
"""
import collections
import time

import requests
from fsspec.spec import AbstractFileSystem

BASE = "https://openmeteo.s3.amazonaws.com/"


class BlockFS(AbstractFileSystem):
    protocol = "blockhttp"
    cachable = False

    def __init__(self, block=1024 * 1024, maxblocks=64, retries=120, wait=10, **kw):
        super().__init__(**kw)
        self.block, self.maxblocks = block, maxblocks
        self.retries, self.wait = retries, wait
        self.session = requests.Session()
        self.sizes = {}
        self.cache = collections.OrderedDict()
        self.http_requests = 0
        self.http_bytes = 0

    def _retry(self, what, fn):
        for attempt in range(self.retries):
            try:
                return fn()
            except (requests.RequestException, IOError) as e:
                if attempt == 0:
                    print(f"   [red] fallo en {what}: {type(e).__name__}. Reintentando cada {self.wait} s...", flush=True)
                time.sleep(self.wait)
        raise IOError(f"sin conexion tras {self.retries * self.wait // 60} minutos ({what})")

    def size(self, path):
        if path not in self.sizes:
            def head():
                r = self.session.head(BASE + path, timeout=60)
                r.raise_for_status()
                return int(r.headers["Content-Length"])
            self.sizes[path] = self._retry(f"tamano de {path}", head)
        return self.sizes[path]

    def info(self, path, **kw):
        return {"name": path, "size": self.size(path), "type": "file"}

    def _blk(self, path, i):
        key = (path, i)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        a, b = i * self.block, min((i + 1) * self.block, self.size(path)) - 1

        def get():
            r = self.session.get(BASE + path, headers={"Range": f"bytes={a}-{b}"}, timeout=120)
            r.raise_for_status()
            if len(r.content) != b - a + 1:
                raise IOError("respuesta incompleta")
            return r.content

        data = self._retry(f"{path} bytes {a}-{b}", get)
        self.http_requests += 1
        self.http_bytes += len(data)
        self.cache[key] = data
        if len(self.cache) > self.maxblocks:
            self.cache.popitem(last=False)
        return data

    def cat_file(self, path, start=None, end=None, **kw):
        size = self.size(path)
        start = 0 if start is None else (start if start >= 0 else size + start)
        end = size if end is None else min(end if end >= 0 else size + end, size)
        out, pos = [], start
        while pos < end:
            i = pos // self.block
            o = pos - i * self.block
            take = min(end - pos, self.block - o)
            out.append(self._blk(path, i)[o:o + take])
            pos += take
        return b"".join(out)
