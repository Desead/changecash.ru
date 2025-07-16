const leftInput = document.getElementById("leftMoneyInput");
const rightInput = document.getElementById("rightMoneyInput");
const leftAmount = document.getElementById("id_left_amount");
const rightAmount = document.getElementById("id_right_amount");
const amountError = document.getElementById("amount-error");

let lastQueryKey = "";
let lastQueryTime = 0;

export function debounce(func, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => func.apply(this, args), delay);
    };
}

function showError(msg) {
    rightAmount.value = "";
    leftAmount.classList.add("is-invalid");
    amountError.textContent = msg;
}

function clearError() {
    leftAmount.classList.remove("is-invalid");
    amountError.textContent = "";
}

export function fetchAndUpdateRate() {
    clearError();

    const left = leftInput.value.trim();
    const right = rightInput.value.trim();
    const amount = leftAmount.value.trim().replace(",", ".");

    if (!left || !right || !amount || isNaN(parseFloat(amount))) {
        showError("Выберите монеты и введите корректную сумму.");
        return;
    }

    const queryKey = `${left}__${right}__${amount}`;
    const now = Date.now();

    if (queryKey === lastQueryKey && now - lastQueryTime < 3000) return;

    lastQueryKey = queryKey;
    lastQueryTime = now;

    fetch(`/api/get-rate/?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}&amount=${encodeURIComponent(amount)}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showError(data.error);
            } else {
                updateUI(data);
            }
        })
        .catch(err => {
            console.error("Ошибка запроса:", err);
            showError("Сервер не отвечает.");
        });
}

function updateUI(data) {
    const amountOut = parseFloat(data.amount_out);
    if (isNaN(amountOut)) {
        rightAmount.value = "";
        return;
    }
    rightAmount.value = amountOut;
}

export function fetchRatePeriodically() {
    setInterval(fetchAndUpdateRate, 3000);
}
