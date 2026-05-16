/**
 * MindMatrix 角色广场模块
 */
function personasModule() {
    return {
        personas: [],

        async fetchPersonas() {
            try {
                const res = await fetch('/api/personas');
                this.personas = await res.json();
                this.$nextTick(() => lucide.createIcons());
            } catch (e) {
                console.error('获取角色失败', e);
            }
        }
    };
}
