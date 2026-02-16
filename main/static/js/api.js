// ManagementAPI - API для работы с управлением данными
const ManagementAPI = {
    // Получить CSRF токен
    getCsrfToken: function() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    },

    // Базовый метод для выполнения запросов
    request: async function(url, method = 'GET', data = null) {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            credentials: 'same-origin'
        };

        if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            
            // Проверяем статус ответа
            if (!response.ok) {
                const errorText = await response.text();
                let errorData;
                try {
                    errorData = JSON.parse(errorText);
                } catch (e) {
                    errorData = { error: errorText || `HTTP ${response.status}: ${response.statusText}` };
                }
                return {
                    success: false,
                    error: errorData.error || errorData.message || `Ошибка сервера: ${response.status}`
                };
            }
            
            const result = await response.json();
            return result;
        } catch (error) {
            console.error('API request error:', error);
            return {
                success: false,
                error: error.message || 'Ошибка соединения с сервером'
            };
        }
    },

    // Товары
    products: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/products/', 'POST', data);
        },
        update: async function(productId, data) {
            return await ManagementAPI.request(`/api/management/products/${productId}/`, 'PUT', data);
        },
        delete: async function(productId) {
            return await ManagementAPI.request(`/api/management/products/${productId}/`, 'DELETE');
        },
        get: async function(productId) {
            return await ManagementAPI.request(`/api/management/products/${productId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/products/', 'GET');
        }
    },

    // Категории
    categories: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/categories/', 'POST', data);
        },
        update: async function(categoryId, data) {
            return await ManagementAPI.request(`/api/management/categories/${categoryId}/`, 'PUT', data);
        },
        delete: async function(categoryId) {
            return await ManagementAPI.request(`/api/management/categories/${categoryId}/`, 'DELETE');
        },
        get: async function(categoryId) {
            return await ManagementAPI.request(`/api/management/categories/${categoryId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/categories/', 'GET');
        }
    },

    // Бренды
    brands: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/brands/', 'POST', data);
        },
        update: async function(brandId, data) {
            return await ManagementAPI.request(`/api/management/brands/${brandId}/`, 'PUT', data);
        },
        delete: async function(brandId) {
            return await ManagementAPI.request(`/api/management/brands/${brandId}/`, 'DELETE');
        },
        get: async function(brandId) {
            return await ManagementAPI.request(`/api/management/brands/${brandId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/brands/', 'GET');
        }
    },

    // Заказы
    orders: {
        list: async function() {
            return await ManagementAPI.request('/api/management/orders/', 'GET');
        },
        get: async function(orderId) {
            return await ManagementAPI.request(`/api/management/orders/${orderId}/`, 'GET');
        },
        updateStatus: async function(orderId, data) {
            return await ManagementAPI.request(`/api/management/orders/${orderId}/`, 'PATCH', data);
        }
    },

    // Пользователи
    users: {
        list: async function() {
            return await ManagementAPI.request('/api/management/users/', 'GET');
        },
        get: async function(userId) {
            return await ManagementAPI.request(`/api/management/users/${userId}/`, 'GET');
        },
        create: async function(data) {
            return await ManagementAPI.request('/api/management/users/', 'POST', data);
        },
        update: async function(userId, data) {
            return await ManagementAPI.request(`/api/management/users/${userId}/`, 'PUT', data);
        },
        delete: async function(userId) {
            return await ManagementAPI.request(`/api/management/users/${userId}/`, 'DELETE');
        },
        toggleBlock: async function(userId) {
            return await ManagementAPI.request(`/api/management/users/${userId}/toggle-block/`, 'POST');
        }
    },

    // Промоакции
    promotions: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/promotions/', 'POST', data);
        },
        update: async function(promoId, data) {
            return await ManagementAPI.request(`/api/management/promotions/${promoId}/`, 'PUT', data);
        },
        delete: async function(promoId) {
            return await ManagementAPI.request(`/api/management/promotions/${promoId}/`, 'DELETE');
        },
        get: async function(promoId) {
            return await ManagementAPI.request(`/api/management/promotions/${promoId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/promotions/', 'GET');
        }
    },

    // Поставщики
    suppliers: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/suppliers/', 'POST', data);
        },
        update: async function(supplierId, data) {
            return await ManagementAPI.request(`/api/management/suppliers/${supplierId}/`, 'PUT', data);
        },
        delete: async function(supplierId) {
            return await ManagementAPI.request(`/api/management/suppliers/${supplierId}/`, 'DELETE');
        },
        get: async function(supplierId) {
            return await ManagementAPI.request(`/api/management/suppliers/${supplierId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/suppliers/', 'GET');
        }
    },

    // Роли
    roles: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/roles/', 'POST', data);
        },
        update: async function(roleId, data) {
            return await ManagementAPI.request(`/api/management/roles/${roleId}/`, 'PUT', data);
        },
        delete: async function(roleId) {
            return await ManagementAPI.request(`/api/management/roles/${roleId}/`, 'DELETE');
        },
        get: async function(roleId) {
            return await ManagementAPI.request(`/api/management/roles/${roleId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/roles/', 'GET');
        }
    },

    // Бэкапы
    backups: {
        create: async function(data) {
            return await ManagementAPI.request('/api/management/backups/', 'POST', data);
        },
        update: async function(backupId, data) {
            return await ManagementAPI.request(`/api/management/backups/${backupId}/`, 'PUT', data);
        },
        delete: async function(backupId) {
            return await ManagementAPI.request(`/api/management/backups/${backupId}/`, 'DELETE');
        },
        get: async function(backupId) {
            return await ManagementAPI.request(`/api/management/backups/${backupId}/`, 'GET');
        },
        list: async function() {
            return await ManagementAPI.request('/api/management/backups/', 'GET');
        }
    }
};

// SupportAPI - API для работы с поддержкой
const SupportAPI = {
    // Получить CSRF токен
    getCsrfToken: function() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    },

    // Базовый метод для выполнения запросов
    request: async function(url, method = 'GET', data = null) {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            credentials: 'same-origin'
        };

        if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            
            // Проверяем статус ответа
            if (!response.ok) {
                const errorText = await response.text();
                let errorData;
                try {
                    errorData = JSON.parse(errorText);
                } catch (e) {
                    errorData = { error: errorText || `HTTP ${response.status}: ${response.statusText}` };
                }
                return {
                    success: false,
                    error: errorData.error || errorData.message || `Ошибка сервера: ${response.status}`
                };
            }
            
            const result = await response.json();
            return result;
        } catch (error) {
            console.error('API request error:', error);
            return {
                success: false,
                error: error.message || 'Ошибка соединения с сервером'
            };
        }
    },

    // Получить список обращений
    list: async function() {
        return await SupportAPI.request('/api/support/', 'GET');
    },

    // Получить конкретное обращение
    get: async function(ticketId) {
        return await SupportAPI.request(`/api/support/${ticketId}/`, 'GET');
    },

    // Создать новое обращение
    create: async function(data) {
        return await SupportAPI.request('/api/support/', 'POST', data);
    },

    // Обновить обращение (ответ менеджера)
    update: async function(ticketId, data) {
        return await SupportAPI.request(`/api/support/${ticketId}/`, 'PUT', data);
    }
};

