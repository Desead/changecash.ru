document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("popular-rates");

    async function fetchPopularRates() {
        try {
            const res = await fetch("/api/popular-rates/");
            const data = await res.json();

            if (!data.rates || !Array.isArray(data.rates)) {
                container.innerHTML = `<div class="col-12 text-danger">Не удалось загрузить курсы</div>`;
                return;
            }

            if (data.rates.length === 0) {
                container.innerHTML = `<div class="col-12 text-muted">Нет популярных курсов</div>`;
                return;
            }

            container.innerHTML = "";

            data.rates.forEach(rate => {
                const left = rate.left || "—";
                const right = rate.right || "—";
                const rateValue = rate.rate ? parseFloat(rate.rate).toString() : "—";

                const col = document.createElement("div");
                col.className = "text-center px-3";
                col.innerHTML = `<span class="rate-label">${left} → ${right}</span><br><strong>${rateValue}</strong>`;

                container.appendChild(col);
            });

        } catch (error) {
            console.error("Ошибка при загрузке курсов:", error);
            container.innerHTML = `<div class="col-12 text-danger">Ошибка при получении данных</div>`;
        }
    }

    fetchPopularRates(); // первичная загрузка
    setInterval(fetchPopularRates, 30000); // автообновление
});
