/**
 * Горячие клавиши для администратора MPTCOURSE
 * Используются комбинации Ctrl+Alt+цифра для быстрого доступа к часто используемым функциям
 */

(function() {
    'use strict';

    // Проверяем, является ли пользователь администратором
    let isAdmin = false;
    try {
        isAdmin = document.body.dataset.isAdmin === 'true';
    } catch (e) {
        console.warn('Ошибка при проверке прав администратора:', e);
        return;
    }
    
    if (!isAdmin) {
        return; // Выходим, если пользователь не админ
    }

    // Карта горячих клавиш - 8 наиболее часто используемых функций (7 цифр + B для бэкапов)
    const shortcuts = {
        // Ctrl+Alt+1 - Панель управления
        'Digit1': {
            url: '/admin/dashboard/',
            description: 'Панель управления',
            keys: 'Ctrl+Alt+1',
            icon: '📊'
        },
        // Ctrl+Alt+2 - Список товаров
        'Digit2': {
            url: '/admin/products/',
            description: 'Список товаров',
            keys: 'Ctrl+Alt+2',
            icon: '📦'
        },
        // Ctrl+Alt+3 - Список заказов
        'Digit3': {
            url: '/admin/orders/',
            description: 'Список заказов',
            keys: 'Ctrl+Alt+3',
            icon: '🛒'
        },
        // Ctrl+Alt+4 - Список пользователей
        'Digit4': {
            url: '/admin/users/',
            description: 'Список пользователей',
            keys: 'Ctrl+Alt+4',
            icon: '👥'
        },
        // Ctrl+Alt+5 - Аналитика
        'Digit5': {
            url: '/admin/analytics/',
            description: 'Аналитика и отчёты',
            keys: 'Ctrl+Alt+5',
            icon: '📈'
        },
        // Ctrl+Alt+6 - Новый товар
        'Digit6': {
            url: '/admin/products/add/',
            description: 'Добавить товар',
            keys: 'Ctrl+Alt+6',
            icon: '➕'
        },
        // Ctrl+Alt+7 - Поддержка
        'Digit7': {
            url: '/admin/support/',
            description: 'Поддержка',
            keys: 'Ctrl+Alt+7',
            icon: '💬'
        },
        // Ctrl+Alt+B - Бэкапы
        'KeyB': {
            url: '/admin/backups/',
            description: 'Резервные копии',
            keys: 'Ctrl+Alt+B',
            icon: '💾'
        }
    };

    // Показываем уведомление о горячей клавише в стиле сайта
    function showShortcutNotification(shortcut) {
        // Удаляем предыдущее уведомление, если есть
        const existing = document.getElementById('shortcut-notification');
        if (existing) {
            existing.remove();
        }

        // Создаем новое уведомление в стиле сайта
        const notification = document.createElement('div');
        notification.id = 'shortcut-notification';
        notification.className = 'shortcut-notification';
        notification.innerHTML = `
            <span class="shortcut-icon">${shortcut.icon}</span>
            <span class="shortcut-text">${shortcut.description}</span>
        `;

        document.body.appendChild(notification);

        // Анимация появления
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);

        // Удаляем уведомление через 2 секунды
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }, 2000);
    }

    // Функция для показа подсказки
    function showShortcutsHelp() {
        // Удаляем существующую подсказку, если есть
        const existing = document.querySelector('.admin-shortcuts-help');
        if (existing) {
            existing.remove();
        }

        const helpText = document.createElement('div');
        helpText.className = 'admin-shortcuts-help';
        helpText.innerHTML = `
            <h4>
                <span>⌨️</span>
                <span>Горячие клавиши</span>
            </h4>
            ${Object.values(shortcuts).map(shortcut => `
                <div class="shortcut-item">
                    <div class="shortcut-label">
                        <span class="shortcut-icon-small">${shortcut.icon}</span>
                        <span>${shortcut.description}</span>
                    </div>
                    <kbd>${shortcut.keys}</kbd>
                </div>
            `).join('')}
            <button class="close-btn" onclick="this.parentElement.remove();">
                Закрыть
            </button>
        `;
        
        document.body.appendChild(helpText);
        
        // Анимация появления
        setTimeout(() => {
            helpText.style.opacity = '0';
            helpText.style.transform = 'translateY(20px)';
            helpText.style.transition = 'all 0.3s ease-out';
            setTimeout(() => {
                helpText.style.opacity = '1';
                helpText.style.transform = 'translateY(0)';
            }, 10);
        }, 10);
    }

    // Обработчик горячих клавиш
    document.addEventListener('keydown', function(e) {
        // Показ подсказки по Ctrl+Alt+? или Ctrl+Alt+H
        if (e.ctrlKey && e.altKey && !e.shiftKey && !e.metaKey && (e.key === '?' || e.key === 'h' || e.key === 'H')) {
            e.preventDefault();
            e.stopPropagation();
            showShortcutsHelp();
            return;
        }

        // Проверяем комбинацию Ctrl+Alt+цифра или Ctrl+Alt+B
        if (e.ctrlKey && e.altKey && !e.shiftKey && !e.metaKey) {
            // Проверяем цифры 1-7
            if (e.code && e.code.startsWith('Digit')) {
                const digit = parseInt(e.code.replace('Digit', ''));
                if (digit >= 1 && digit <= 7) {
                    const shortcut = shortcuts[e.code];
                    
                    if (shortcut) {
                        e.preventDefault();
                        e.stopPropagation();
                        e.stopImmediatePropagation();
                        
                        // Показываем уведомление
                        showShortcutNotification(shortcut);
                        
                        // Небольшая задержка для показа уведомления перед переходом
                        setTimeout(() => {
                            // Используем window.location.assign для более надежного перехода
                            try {
                                window.location.assign(shortcut.url);
                            } catch (err) {
                                // Если assign не работает, используем href
                                window.location.href = shortcut.url;
                            }
                        }, 100);
                    }
                }
            }
            // Проверяем букву B для бэкапов
            else if (e.code === 'KeyB' || e.key === 'b' || e.key === 'B') {
                const shortcut = shortcuts['KeyB'];
                
                if (shortcut) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    
                    // Показываем уведомление
                    showShortcutNotification(shortcut);
                    
                    // Небольшая задержка для показа уведомления перед переходом
                    setTimeout(() => {
                        try {
                            window.location.assign(shortcut.url);
                        } catch (err) {
                            window.location.href = shortcut.url;
                        }
                    }, 100);
                }
            }
        }
    }, true); // Используем capture phase для перехвата события раньше других обработчиков

    // Добавляем стили для уведомлений и подсказки в стиле сайта
    if (!document.getElementById('admin-shortcuts-styles')) {
        const style = document.createElement('style');
        style.id = 'admin-shortcuts-styles';
        style.textContent = `
            /* Уведомление о горячей клавише */
            .shortcut-notification {
                position: fixed;
                top: 20px;
                right: 20px;
                background: var(--bg-color, #ffffff);
                color: var(--text-color, #1a1a1a);
                border: 1px solid var(--border, #000);
                border-radius: 10px;
                padding: 12px 20px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 10000;
                font-size: 14px;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 10px;
                opacity: 0;
                transform: translateX(100%);
                transition: all 0.3s ease-out;
                pointer-events: none;
                max-width: 300px;
            }
            
            .shortcut-notification.show {
                opacity: 1;
                transform: translateX(0);
            }
            
            .shortcut-icon {
                font-size: 18px;
            }
            
            .shortcut-text {
                flex: 1;
            }
            
            .dark-theme .shortcut-notification {
                border-color: var(--border, #fff);
            }
            
            /* Подсказка с горячими клавишами */
            .admin-shortcuts-help {
                position: fixed;
                bottom: 20px;
                left: 20px;
                background: var(--bg-color, #ffffff);
                color: var(--text-color, #1a1a1a);
                border: 1px solid var(--border, #000);
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.12);
                z-index: 9999;
                font-size: 13px;
                max-width: 320px;
                line-height: 1.6;
            }
            
            .dark-theme .admin-shortcuts-help {
                border-color: var(--border, #fff);
            }
            
            .admin-shortcuts-help h4 {
                margin: 0 0 12px 0;
                font-size: 16px;
                font-weight: 700;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .admin-shortcuts-help .shortcut-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid var(--border, #ddd);
            }
            
            .admin-shortcuts-help .shortcut-item:last-child {
                border-bottom: none;
            }
            
            .admin-shortcuts-help .shortcut-label {
                display: flex;
                align-items: center;
                gap: 8px;
                flex: 1;
            }
            
            .admin-shortcuts-help .shortcut-icon-small {
                font-size: 16px;
            }
            
            .admin-shortcuts-help kbd {
                background: var(--surface, #f5f5f5);
                color: var(--text-color, #1a1a1a);
                border: 1px solid var(--border, #ccc);
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
                font-size: 11px;
                font-weight: 600;
                box-shadow: 0 1px 2px rgba(0,0,0,0.1);
            }
            
            .dark-theme .admin-shortcuts-help kbd {
                background: var(--surface, #2a2a2a);
                border-color: var(--border, #555);
            }
            
            .admin-shortcuts-help .close-btn {
                margin-top: 12px;
                width: 100%;
                padding: 8px 16px;
                background: var(--bg-color, #ffffff);
                color: var(--text-color, #1a1a1a);
                border: 1px solid var(--border, #000);
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 500;
                transition: all 0.2s ease;
            }
            
            .admin-shortcuts-help .close-btn:hover {
                background: var(--text-color, #000);
                color: var(--bg-color, #fff);
            }
            
            .dark-theme .admin-shortcuts-help .close-btn:hover {
                background: var(--text-color, #fff);
                color: var(--bg-color, #000);
            }
            
            @media (max-width: 768px) {
                .admin-shortcuts-help {
                    left: 10px;
                    right: 10px;
                    max-width: none;
                    bottom: 10px;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // Показываем подсказку при первом заходе
    if (!localStorage.getItem('admin-shortcuts-shown')) {
        setTimeout(() => {
            const helpText = document.createElement('div');
            helpText.className = 'admin-shortcuts-help';
            helpText.innerHTML = `
                <h4>
                    <span>⌨️</span>
                    <span>Горячие клавиши</span>
                </h4>
                ${Object.values(shortcuts).map(shortcut => `
                    <div class="shortcut-item">
                        <div class="shortcut-label">
                            <span class="shortcut-icon-small">${shortcut.icon}</span>
                            <span>${shortcut.description}</span>
                        </div>
                        <kbd>${shortcut.keys}</kbd>
                    </div>
                `).join('')}
                <button class="close-btn" onclick="this.parentElement.remove(); localStorage.setItem('admin-shortcuts-shown', 'true');">
                    Понятно
                </button>
            `;
            
            document.body.appendChild(helpText);
        }, 1000);
    }
})();

