/**
 * MindMatrix 认证模块
 */
function authModule() {
    return {
        isLoggedIn: false,
        showAuth: false,
        authMode: 'login',
        loading: false,
        user: { username: '', balance: '0.00' },
        authForm: { username: '', password: '', invite_code: '' },

        async checkAuth() {
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    await this.fetchMe();
                    this.isLoggedIn = true;
                    this.loadConversations();
                } catch (e) {
                    localStorage.removeItem('token');
                }
            }
        },

        async fetchMe() {
            const res = await window.apiClient.call('/api/me');
            if (res) {
                this.user = { username: res.username, balance: res.balance.toFixed(2) };
            }
        },

        openAuth(mode) {
            this.authMode = mode;
            this.showAuth = true;
        },

        async handleAuth() {
            this.loading = true;
            try {
                const endpoint = this.authMode === 'login' ? '/api/login' : '/api/register';
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.authForm)
                });
                const data = await res.json();
                if (!res.ok) {
                    let errMsg = data.detail || '认证失败';
                    if (Array.isArray(data.detail)) {
                        const fieldMap = { 'username': '用户名', 'password': '密码', 'invite_code': '邀请码' };
                        errMsg = data.detail.map(err => {
                            const field = err.loc[err.loc.length - 1];
                            const fieldName = fieldMap[field] || field;
                            let msg = err.msg;
                            if (msg.includes('at least')) {
                                const min = msg.match(/at least (\d+)/)?.[1] || '';
                                msg = `长度不能少于 ${min} 个字符`;
                            } else if (msg.includes('at most')) {
                                const max = msg.match(/at most (\d+)/)?.[1] || '';
                                msg = `长度不能超过 ${max} 个字符`;
                            } else if (msg.includes('field required')) {
                                msg = `不能为空`;
                            }
                            return `• ${fieldName}：${msg}`;
                        }).join('\n');
                    }
                    throw new Error(errMsg);
                }

                if (this.authMode === 'register') {
                    this.authMode = 'login';
                    await this.handleAuth();
                    return;
                }

                localStorage.setItem('token', data.access_token);
                this.isLoggedIn = true;
                this.showAuth = false;
                await this.fetchMe();
                this.loadConversations();
                this.authForm = { username: '', password: '', invite_code: '' };
            } catch (e) {
                alert(e.message);
            } finally {
                this.loading = false;
            }
        },

        logout() {
            localStorage.removeItem('token');
            location.reload();
        }
    };
}
