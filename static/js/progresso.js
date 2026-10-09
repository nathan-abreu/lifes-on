(function () {
    'use strict';
    function criarGrafico(canvasId, dadosId, erroId, tipo, campo, legenda) {
    var canvas = document.getElementById(canvasId);
    var dados = document.getElementById(dadosId);
    if (!canvas || !dados) return;
    if (typeof Chart === 'undefined') {
        document.getElementById(erroId).hidden = false;
        return;
    }
    var serie = JSON.parse(dados.textContent);
    new Chart(canvas, {
        type: tipo,
        data: {
            labels: serie.labels,
            datasets: [{
                label: legenda,
                data: serie[campo],
                borderColor: '#3c6b91',
                backgroundColor: tipo === 'bar' ? '#3c6b91' : 'rgba(60, 107, 145, 0.07)',
                fill: true,
                tension: 0.25
            }]
        },
        options: {
            animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : {duration: 350},
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
            plugins: { legend: { display: false } }
        }
    });
    }
    criarGrafico('graficoProgresso', 'dadosProgresso', 'graficoErro', 'line', 'minutos', 'Minutos registrados');
    criarGrafico('graficoMensal', 'dadosMensais', 'graficoMensalErro', 'bar', 'atividades', 'Atividades registradas');
})();
