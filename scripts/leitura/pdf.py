#!/usr/bin/env python3
"""Texto de PDF: pdftotext pagina a pagina; OCR (tesseract, portugues) nas
paginas que vem praticamente sem texto.

Binarios do sistema (lenovo-claude): poppler-utils (pdfinfo, pdftotext,
pdftoppm) e tesseract-ocr + tesseract-ocr-por. Sem dependencia pip.

Por que a decisao e' por pagina: o Ato Conjunto RFB/CGIBS de 29/05/2026 e'
"Microsoft: Print To PDF" — imagem pura; o pdftotext devolve so' o carimbo
da assinatura digital (156 caracteres). Um limiar no documento inteiro nao
pegaria um PDF misto (paginas de texto + paginas escaneadas).

OCR e' lento (segundos por pagina) e isso e' aceito: o orcamento da raia de
leitura (ler_textos.ORCAMENTO_S) e' de 45 min e o backfill roda sem limite.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LIMIAR_PAGINA = 300          # caracteres nao-brancos abaixo disto -> tenta OCR
DPI_OCR = 300
TIMEOUT_TEXTO_S = 120
TIMEOUT_OCR_S = 600          # por pagina: lento e tudo bem, so' nao pode travar


class ErroPDF(Exception):
    pass


def _roda(cmd, timeout=TIMEOUT_TEXTO_S):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ErroPDF(f"{cmd[0]} passou de {timeout}s") from e
    except FileNotFoundError as e:
        raise ErroPDF(f"{cmd[0]} nao instalado") from e
    if r.returncode != 0:
        raise ErroPDF(f"{cmd[0]} saiu com {r.returncode}: "
                      f"{r.stderr[:200].decode('utf-8', 'replace').strip()}")
    return r.stdout


def tem_ocr():
    return shutil.which("tesseract") is not None


def num_paginas(arq):
    saida = _roda(["pdfinfo", str(arq)]).decode("utf-8", "replace")
    m = re.search(r"^Pages:\s+(\d+)", saida, re.M)
    if not m:
        raise ErroPDF("pdfinfo sem contagem de paginas")
    return int(m.group(1))


def texto_pagina(arq, n):
    return _roda(["pdftotext", "-layout", "-enc", "UTF-8", "-f", str(n), "-l", str(n),
                  str(arq), "-"]).decode("utf-8", "replace")


def ocr_pagina(arq, n, pasta):
    raiz = Path(pasta) / f"ocr-p{n}"
    _roda(["pdftoppm", "-r", str(DPI_OCR), "-gray", "-png", "-singlefile",
           "-f", str(n), "-l", str(n), str(arq), str(raiz)], timeout=TIMEOUT_OCR_S)
    png = raiz.with_suffix(".png")
    try:
        return _roda(["tesseract", str(png), "stdout", "-l", "por"],
                     timeout=TIMEOUT_OCR_S).decode("utf-8", "replace")
    finally:
        png.unlink(missing_ok=True)


def _uteis(t):
    return len(re.sub(r"\s+", "", t or ""))


def extrai_pdf(dados):
    with tempfile.TemporaryDirectory(prefix="leitura-pdf-") as pasta:
        arq = Path(pasta) / "doc.pdf"
        arq.write_bytes(dados)
        n = num_paginas(arq)
        partes, ocr, sem_ocr = [], [], []
        for i in range(1, n + 1):
            t = texto_pagina(arq, i)
            if _uteis(t) < LIMIAR_PAGINA:
                if not tem_ocr():
                    sem_ocr.append(i)
                else:
                    o = ocr_pagina(arq, i, pasta)
                    if _uteis(o) > _uteis(t):
                        t = o
                        ocr.append(i)
            partes.append(f"[pagina {i}]\n{t.strip()}")
    if sem_ocr:
        raise ErroPDF(f"paginas {sem_ocr} sem texto e tesseract nao instalado")
    return {"texto": "\n\n".join(partes), "paginas": n, "paginas_ocr": ocr,
            "origem": "pdf+ocr" if ocr else "pdf"}
