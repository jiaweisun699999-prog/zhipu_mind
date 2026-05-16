"""
MindMatrix —— RAG 模块
向量模型全局单例 + Persona 注册表扫描 + 语义检索。
向量数据按需从磁盘读取，用完即丢，适配 2核2G 小内存服务器。
"""
import re
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import HTTPException

from app.config import PERSONAS_DIR, ROOT_DIR, logger

sys.path.append(str(ROOT_DIR))
from tools.search import load_index, cosine_similarity

try:
    from fastembed import TextEmbedding
except ImportError:
    raise RuntimeError("fastembed 未安装，请先运行 pip install fastembed")

# ── 全局向量模型单例（只加载一次防止 OOM）────────────────────────────────────
_sample_index_path = next(PERSONAS_DIR.rglob("vector_index.json"), None)
if _sample_index_path is None:
    raise RuntimeError("找不到任何 vector_index.json，请先运行 build_index.py")

_sample_index = load_index(str(_sample_index_path))
_embed_model  = TextEmbedding(model_name=_sample_index["model"])
del _sample_index  # 立即释放，只保留模型本身
logger.info("向量模型已加载，所有角色共享同一实例")

# ── 全局角色注册表（只存元数据，不存向量）───────────────────────────────────
AVAILABLE_PERSONAS: Dict[str, Dict[str, Any]] = {}


def _parse_skill_frontmatter(skill_path: Path) -> Dict[str, str]:
    """解析 SKILL.md 的 YAML frontmatter 和 H1 标题，提取展示名和描述。"""
    try:
        text = skill_path.read_text(encoding="utf-8")

        h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        h1_name  = ""
        if h1_match:
            h1_name = h1_match.group(1).split("·")[0].split("视角")[0].strip()

        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm_match:
            return {"name": h1_name} if h1_name else {}

        fm_block   = fm_match.group(1)
        name_match = re.search(r"^name:\s*(.+)$", fm_block, re.MULTILINE)
        name       = name_match.group(1).strip() if name_match else h1_name

        # H1 含中文或空格时优先使用
        if h1_name and (re.search(r"[\u4e00-\u9fa5]", h1_name) or " " in h1_name):
            name = h1_name

        desc_match = re.search(r"^description:\s*\|?\s*\n((?:[ \t]+.+\n?)+)", fm_block, re.MULTILINE)
        if desc_match:
            desc = " ".join(l.strip() for l in desc_match.group(1).splitlines() if l.strip())
        else:
            inline = re.search(r"^description:\s*(.+)$", fm_block, re.MULTILINE)
            desc   = inline.group(1).strip() if inline else ""

        return {"name": name, "description": desc}
    except Exception as e:
        logger.warning(f"解析 frontmatter 失败 {skill_path}: {e}")
        return {}


def scan_personas() -> None:
    """
    启动时扫描 personas/ 目录，将每个角色元数据注册到 AVAILABLE_PERSONAS。
    内存中只保留 id / name / description / skill_path / index_path，不加载向量。
    """
    AVAILABLE_PERSONAS.clear()

    for persona_dir in sorted(PERSONAS_DIR.iterdir()):
        if not persona_dir.is_dir():
            continue
        persona_id = persona_dir.name

        skill_path = persona_dir / "SKILL.md"
        if not skill_path.exists():
            if persona_id == "hu-chenfeng":
                skill_path = ROOT_DIR / "SKILL.md"
            else:
                logger.warning(f"[personas] {persona_id} 缺少 SKILL.md，跳过")
                continue

        index_path = persona_dir / "vector_index.json"
        if not index_path.exists():
            logger.warning(f"[personas] {persona_id} 缺少 vector_index.json，跳过")
            continue

        fm           = _parse_skill_frontmatter(skill_path)
        display_name = fm.get("name") or persona_id
        description  = fm.get("description") or f"{display_name} 数字分身"

        AVAILABLE_PERSONAS[persona_id] = {
            "id":          persona_id,
            "name":        display_name,
            "description": description,
            "skill_path":  str(skill_path),
            "index_path":  str(index_path),
        }

    logger.info(
        f"[personas] 扫描完成，共注册 {len(AVAILABLE_PERSONAS)} 个角色："
        f"{list(AVAILABLE_PERSONAS.keys())}"
    )


def get_persona_or_404(persona_id: str) -> Dict[str, Any]:
    """从注册表获取角色信息，不存在则抛 404。"""
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail=f"角色 '{persona_id}' 不存在")
    return persona


def search_quotes_for_persona(query: str, persona_id: str, top_k: int = 5) -> list[dict]:
    """
    懒加载指定角色的 vector_index.json，执行语义检索后立即释放。
    全程不在内存中持久保留向量数据。
    """
    persona = AVAILABLE_PERSONAS.get(persona_id)
    if not persona:
        return []
    try:
        index     = load_index(persona["index_path"])
        query_emb = list(_embed_model.embed([query]))[0].tolist()
        scored    = [
            {"text": chunk["text"], "score": cosine_similarity(query_emb, chunk["embedding"])}
            for chunk in index["chunks"]
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
    except Exception as e:
        logger.error(f"[RAG] 角色 {persona_id} 检索失败: {e}")
        return []
