/**
 * Встроенный PDF-ридер на PDF.js.
 * data-pdf-url — URL PDF; data-pdf-page — начальная страница; data-pdf-page-end — конечная (диапазон). Выводятся только указанные страницы.
 */
(function() {
    var PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174';
    var loaded = false;
    var loading = null;

    function loadPdfJs() {
        if (loaded) return Promise.resolve();
        if (loading) return loading;
        loading = new Promise(function(resolve, reject) {
            var script = document.createElement('script');
            script.src = PDFJS_CDN + '/pdf.min.js';
            script.onload = function() {
                if (window.pdfjsLib && window.pdfjsLib.GlobalWorkerOptions) {
                    window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_CDN + '/pdf.worker.min.js';
                }
                loaded = true;
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
        return loading;
    }

    function renderPdfViewer(container) {
        var url = (container.getAttribute('data-pdf-url') || '').trim();
        var initialPage = parseInt(container.getAttribute('data-pdf-page'), 10) || 1;
        var pageEndRaw = (container.getAttribute('data-pdf-page-end') || '').trim();
        var pageEnd = pageEndRaw ? parseInt(pageEndRaw, 10) : null;
        if (!url) return;

        container.innerHTML = '<div class="pdf-viewer-toolbar">' +
            '<span class="pdf-viewer-pages">Страница <span class="pdf-viewer-current">1</span> из <span class="pdf-viewer-total">1</span></span>' +
            '<div class="pdf-viewer-nav">' +
            '<button type="button" class="pdf-viewer-btn pdf-viewer-prev" title="Предыдущая"><span class="pdf-viewer-arrow">←</span></button>' +
            '<button type="button" class="pdf-viewer-btn pdf-viewer-next" title="Следующая"><span class="pdf-viewer-arrow">→</span></button>' +
            '</div>' +
            '<span class="pdf-viewer-zoom">' +
            '<button type="button" class="pdf-viewer-btn pdf-viewer-zoom-out" title="Уменьшить">−</button>' +
            '<span class="pdf-viewer-scale">100%</span>' +
            '<button type="button" class="pdf-viewer-btn pdf-viewer-zoom-in" title="Увеличить">+</button>' +
            '</span></div><div class="pdf-viewer-canvas-wrap"><canvas class="pdf-viewer-canvas"></canvas></div>';
        var canvas = container.querySelector('.pdf-viewer-canvas');
        var currentSpan = container.querySelector('.pdf-viewer-current');
        var totalSpan = container.querySelector('.pdf-viewer-total');
        var scaleSpan = container.querySelector('.pdf-viewer-scale');
        var pdfDoc = null;
        var pageMin = 1;
        var pageMax = 1;
        var currentPageNum = initialPage;
        var scale = 1.2;

        function renderPage(num) {
            if (!pdfDoc) return;
            var pageNum = Math.max(pageMin, Math.min(pageMax, num));
            pdfDoc.getPage(pageNum).then(function(page) {
                var viewport = page.getViewport({ scale: scale });
                canvas.height = viewport.height;
                canvas.width = viewport.width;
                page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport });
                var indexInRange = pageNum - pageMin + 1;
                if (currentSpan) currentSpan.textContent = indexInRange;
                container.querySelector('.pdf-viewer-prev').disabled = pageNum <= pageMin;
                container.querySelector('.pdf-viewer-next').disabled = pageNum >= pageMax;
            }).catch(function() {
                if (currentSpan) currentSpan.textContent = '—';
            });
        }

        function setScale(s) {
            scale = Math.max(0.5, Math.min(3, s));
            if (scaleSpan) scaleSpan.textContent = Math.round(scale * 100) + '%';
            renderPage(currentPageNum);
        }

        loadPdfJs().then(function() {
            return window.pdfjsLib.getDocument({ url: url }).promise;
        }).then(function(pdf) {
            pdfDoc = pdf;
            pageMin = Math.max(1, initialPage);
            pageMax = pageEnd && pageEnd >= pageMin ? Math.min(pdf.numPages, pageEnd) : pageMin;
            if (pageMax < pageMin) pageMax = pageMin;
            currentPageNum = Math.min(Math.max(pageMin, currentPageNum), pageMax);
            var totalInRange = pageMax - pageMin + 1;
            if (totalSpan) totalSpan.textContent = totalInRange;
            renderPage(currentPageNum);
        }).catch(function(err) {
            container.querySelector('.pdf-viewer-canvas-wrap').innerHTML =
                '<p class="pdf-viewer-error">Не удалось загрузить PDF. <a href="' + url + '" target="_blank" rel="noopener">Открыть в новой вкладке</a>.</p>';
        });

        container.querySelector('.pdf-viewer-prev').addEventListener('click', function() {
            if (currentPageNum > pageMin) { currentPageNum--; renderPage(currentPageNum); }
        });
        container.querySelector('.pdf-viewer-next').addEventListener('click', function() {
            if (pdfDoc && currentPageNum < pageMax) { currentPageNum++; renderPage(currentPageNum); }
        });
        container.querySelector('.pdf-viewer-zoom-in').addEventListener('click', function() { setScale(scale + 0.2); });
        container.querySelector('.pdf-viewer-zoom-out').addEventListener('click', function() { setScale(scale - 0.2); });
    }

    function initAll() {
        document.querySelectorAll('.pdf-viewer-container').forEach(renderPdfViewer);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
    window.initPdfViewers = function() { initAll(); };
    window.renderOnePdfViewer = function(el) {
        if (el && el.classList.contains('pdf-viewer-container')) renderPdfViewer(el);
    };
})();
