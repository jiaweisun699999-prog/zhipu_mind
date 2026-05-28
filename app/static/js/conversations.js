/**
 * MindMatrix 会话管理模块
 */
function conversationsModule() {
    return {
        conversations: [],
        activeConvId: null,
        activeConvTitle: '新对话',
        currentPersona: { id: '', name: '', description: '' },
        sidebarOpen: false,

        async loadConversations() {
            try {
                this.conversations = await window.apiClient.call('/api/conversations');
            } catch (e) {
                console.error('获取会话失败', e);
            }
        },

        async createNewConv(persona) {
            try {
                const res = await window.apiClient.call('/api/conversations', 'POST', {
                    title: `与 ${persona.name} 的对话`,
                    persona_id: persona.id
                });
                this.conversations.unshift(res);
                this.currentPersona = { id: persona.id, name: persona.name };
                await this.loadConversation(res);
            } catch (e) {
                alert(e.message);
            }
        },

        async loadConversation(conv) {
            this.activeConvId = conv.id;
            this.activeConvTitle = conv.title;
            this.currentPersona = {
                id: conv.persona_id,
                name: conv.persona_name || conv.persona_id,
                has_voice: conv.has_voice // 假设后端会话信息也带了这个，或者我们从 personas 列表里找
            };
            // 为了稳妥，如果 conv 里没带，我们可以去 this.personas 里匹配一下
            const p = this.personas.find(p => p.id === conv.persona_id);
            if (p) this.currentPersona.has_voice = p.has_voice;

            // 如果当前角色不支持语音，强制关闭语音模式
            if (!this.currentPersona.has_voice) {
                this.voiceMode = false;
            }

            this.currentView = 'chat';
            this.messages = [];
            this.sidebarOpen = false;

            try {
                const msgs = await window.apiClient.call(`/api/conversations/${conv.id}/messages`);
                this.messages = msgs;
                this.scrollToBottom();
                this.$nextTick(() => lucide.createIcons());
            } catch (e) {
                console.error('加载消息失败', e);
            }
        },

        async deleteConv(id) {
            if (!confirm('确定删除此对话吗？')) return;
            try {
                await window.apiClient.call(`/api/conversations/${id}`, 'DELETE');
                this.conversations = this.conversations.filter(c => c.id !== id);
                if (this.activeConvId === id) {
                    this.currentView = 'plaza';
                    this.activeConvId = null;
                }
            } catch (e) {
                alert(e.message);
            }
        }
    };
}
