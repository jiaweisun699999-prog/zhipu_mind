#!/usr/bin/env python3
"""
通用版本：将任意角色的 Markdown 参考资料切片、嵌入并构建向量索引。

用法:
    python3 tools/build_index.py /path/to/personas/elon-musk
输出:
    /path/to/personas/elon-musk/vector_index.json
"""

import base64
import json
import os
import re
import struct
import sys
from pathlib import Path


def split_into_chunks(text: str, date: str, max_chars: int = 1500) -> list[dict]:
    """通用切片逻辑：按段落（双换行）切分，不再强依赖特定人名。"""
    chunks = []
    # 按双换行符分割段落
    paragraphs = re.split(r'\n\s*\n', text)

    current_chunk = ""

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue

        if len(current_chunk) + len(p) > max_chars and current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "date": date,
                "speaker": "unknown",  # 通用版默认不强行提取说话人
            })
            current_chunk = p
        else:
            current_chunk += "\n\n" + p if current_chunk else p

    if current_chunk.strip():
        chunks.append({
            "text": current_chunk.strip(),
            "date": date,
            "speaker": "unknown",
        })

    return chunks


def extract_date_from_filename(filepath: str) -> str:
    basename = Path(filepath).stem
    match = re.search(r'(\d{4}-\d{2}-\d{2})', basename)
    return match.group(1) if match else basename


def load_transcripts(source_dir: str) -> list[dict]:
    all_chunks = []
    source_path = Path(source_dir)

    # 查找该角色目录下所有的 .md 文件（通常在 references 文件夹中）
    md_files = sorted(source_path.rglob("*.md"))
    skip_names = {"README.md", "README_EN.md", "README_JA.md", "SKILL.md", "SUMMARY.md"}
    md_files = [f for f in md_files if f.name not in skip_names and not f.name.startswith(".")]

    print(f"找到 {len(md_files)} 个知识库文件")

    for md_file in md_files:
        date = extract_date_from_filename(str(md_file))
        text = md_file.read_text(encoding="utf-8")

        if len(text.strip()) < 50:
            continue

        chunks = split_into_chunks(text, date)
        for j, chunk in enumerate(chunks):
            chunk["id"] = f"{date}_{j}"
            chunk["source"] = str(md_file.relative_to(source_path))

        all_chunks.extend(chunks)

    print(f"共生成 {len(all_chunks)} 个文本块")
    return all_chunks


def build_embeddings(chunks: list[dict], model_name: str = "BAAI/bge-small-zh-v1.5") -> list[dict]:
    from fastembed import TextEmbedding
    print(f"加载嵌入模型: {model_name} ...")
    model = TextEmbedding(model_name=model_name)
    texts = [c["text"] for c in chunks]
    print(f"正在生成 {len(texts)} 个向量，请耐心等待...")
    embeddings = list(model.embed(texts, batch_size=32))

    for i, emb in enumerate(embeddings):
        chunks[i]["embedding"] = emb.tolist()
    return chunks


def save_index(chunks: list[dict], output_path: str):
    if not chunks:
        print("没有提取到任何文本块，跳过生成索引。")
        return

    index = {
        "model": "BAAI/bge-small-zh-v1.5",
        "dimension": len(chunks[0]["embedding"]),
        "embedding_format": "base64_float16",
        "count": len(chunks),
        "chunks": []
    }

    for c in chunks:
        emb = c["embedding"]
        binary = struct.pack(f'{len(emb)}e', *emb)
        emb_b64 = base64.b64encode(binary).decode('ascii')

        text = c["text"]
        if len(text) > 1200: text = text[:1200]

        index["chunks"].append({
            "id": c["id"],
            "text": text,
            "date": c["date"],
            "source": c["source"],
            "embedding": emb_b64,
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(',', ':'))

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"✅ 专属索引已保存: {output_path} ({size_mb:.1f} MB)")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 tools/build_index.py /path/to/persona_folder")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    if not source_dir.is_dir():
        print(f"错误: 目录不存在 {source_dir}")
        sys.exit(1)

    # 重点修改：将 json 保存在传入的角色目录下！
    output_path = str(source_dir / "vector_index.json")

    print(f"\n======================================")
    print(f"开始为角色构建向量记忆库: {source_dir.name}")
    print(f"======================================")

    chunks = load_transcripts(source_dir)
    if chunks:
        chunks = build_embeddings(chunks)
        save_index(chunks, output_path)


if __name__ == "__main__":
    main()