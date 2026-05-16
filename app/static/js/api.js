/**
 * MindMatrix API 客户端模块
 * 统一处理认证 Header 与错误响应
 */
window.apiClient = {
    async call(url, method = 'GET', body = null, isFormData = false) {
        const token = localStorage.getItem('token');
        const options = {
            method,
            headers: {}
        };

        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }

        if (body) {
            if (isFormData) {
                options.body = body;
                // 注意：FormData 不要手动设置 Content-Type，由浏览器自动处理
            } else {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(body);
            }
        }

        const res = await fetch(url, options);

        // 处理 401 自动登出
        if (res.status === 401 && !url.includes('/login') && !url.includes('/register')) {
            localStorage.removeItem('token');
            window.dispatchEvent(new CustomEvent('auth-required'));
            return null;
        }

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || '请求失败');
        }
        return data;
    }
};
