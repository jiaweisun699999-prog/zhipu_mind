/**
 * MindMatrix 智谱矩阵 —— 前端核心组合层 v3.0
 * 将各个功能模块聚合到 Alpine.js 组件中
 */

function app() {
    return {
        // ── 基础视图状态 ──────────────────────────────────────────────────
        currentView: 'plaza', // plaza | chat

        // ── 模块组合 ──────────────────────────────────────────────────────
        ...authModule(),        // 认证、用户信息
        ...personasModule(),    // 角色数据
        ...conversationsModule(), // 会话管理
        ...chatModule(),        // 消息收发
        ...recorderModule(),    // 录音逻辑

        // ── 初始化 ────────────────────────────────────────────────────────
        init() {
            // 1. 检查登录态
            this.checkAuth();
            
            // 2. 加载角色列表
            this.fetchPersonas();

            // 3. 轮询刷新余额
            setInterval(() => { 
                if (this.isLoggedIn) this.fetchMe(); 
            }, 30000);

            // 4. 监听全局事件
            window.addEventListener('auth-required', () => {
                this.isLoggedIn = false;
                this.showAuth = true;
            });
        },

        // ── 全局 UI 逻辑 ──────────────────────────────────────────────────
        showPlaza() {
            this.currentView = 'plaza';
            this.activeConvId = null;
            this.$nextTick(() => lucide.createIcons());
        },

        openSidebar() {
            this.sidebarOpen = true;
            this.$nextTick(() => lucide.createIcons());
        }
    };
}
