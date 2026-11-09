import re
import numpy as np
import pymupdf
from app.core.errors import AppError
from app.services.document_service import original_pdf_path, load_document
from app.document.ocr.ocr_service import _engine


def extract_images(document_id: str) -> list[dict]:
    document = load_document(document_id)
    extension = document.get('extension') or document.get('filename', '').rsplit('.', 1)[-1].lower()
    if extension in {'.png', '.jpg', '.jpeg'}:
        from app.services.document_service import original_file_path
        path, _ = original_file_path(document_id)
        raw_bytes = path.read_bytes()
        try:
            with pymupdf.open(stream=raw_bytes, filetype=extension.lstrip('.')) as image:
                page = image[0]
                return [{'document_id': document_id, 'filename': document['filename'],
                         'page': 1, 'image_index': 1, 'width': page.rect.width,
                         'height': page.rect.height, 'caption': '', 'extension': extension,
                         'preview_available': True, '_bytes': raw_bytes}]
        except Exception:
            raise AppError('IMAGE_PARSE_FAILED', '图片文件解析失败', 422) from None
    if extension not in {'pdf', '.pdf'}:
        raise AppError('IMAGE_NOT_FOUND', '当前材料没有可分析的图片页面', 422)
    path, _ = original_pdf_path(document_id)
    images = []
    with pymupdf.open(path) as pdf:
        for page_number, page in enumerate(pdf, 1):
            for image_index, entry in enumerate(page.get_images(full=True)[:20], 1):
                xref = entry[0]
                raw = pdf.extract_image(xref)
                nearby = page.get_text('text')
                images.append({'document_id': document_id, 'filename': document['filename'],
                               'page': page_number, 'image_index': image_index,
                               'width': raw['width'], 'height': raw['height'],
                               'extension': '.pdf', 'preview_available': True,
                               'caption': next((line for line in nearby.splitlines()
                                                if any(word in line for word in ('架构图', '流程图', '示意图'))), ''),
                               '_bytes': raw['image']})
    return images


def _ocr_labels(image_bytes: bytes) -> list[dict]:
    pix = pymupdf.Pixmap(image_bytes)
    if pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
    lines, _ = _engine()(samples)
    return [{'text': item[1].strip(), 'confidence': round(float(item[2]), 3), 'bbox': item[0]}
            for item in (lines or []) if item[1].strip() and float(item[2]) >= .55]


def query_image(document_id: str, question: str) -> dict:
    images = extract_images(document_id)
    if not images:
        raise AppError('IMAGE_NOT_FOUND', '所选 PDF 没有可提取的内嵌图片', 422)
    page_match = re.search(r'第\s*(\d+)\s*页', question)
    image_match = re.search(r'第\s*(\d+)\s*张', question)
    matches = [item for item in images
               if (not page_match or item['page'] == int(page_match.group(1)))
               and (not image_match or item['image_index'] == int(image_match.group(1)))]
    if not matches:
        raise AppError('IMAGE_NOT_FOUND', '指定页码或图片序号没有对应图片', 422)
    image = matches[0]
    labels = _ocr_labels(image['_bytes'])
    if not labels:
        raise AppError('IMAGE_TEXT_UNREADABLE', '图片文字不可辨；当前仅提取 OCR 可读标签，不能猜测图中内容', 422)
    kind = ('architecture_diagram' if '架构' in image['caption'] or '架构' in question else
            'flowchart' if '流程' in image['caption'] or '流程' in question else 'image')
    entities = list(dict.fromkeys(item['text'] for item in labels))[:20]
    description = ('图中可辨识的模块' if kind == 'architecture_diagram' else
                   '图中可辨识的步骤' if kind == 'flowchart' else '图片中可辨识的文字')
    source = {key: value for key, value in image.items() if key != '_bytes'}
    source.update({'type': kind, 'description': f"{description}：{'、'.join(entities)}。",
                   'entities': entities, 'ocr_labels': labels,
                   'confidence': round(sum(item['confidence'] for item in labels) / len(labels), 3)})
    return {'answer': source['description'], 'image': source, 'sources': [source]}
