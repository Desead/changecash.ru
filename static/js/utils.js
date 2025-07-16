import { fetchAndUpdateRate, debounce } from "./api.js";

export function setupAmountHandlers() {
    const leftAmount = document.getElementById("id_left_amount");

    const debouncedFetch = debounce(fetchAndUpdateRate, 400);

    leftAmount?.addEventListener("input", (e) => {
        e.target.value = e.target.value.replace(/[^0-9.,]/g, "");
        debouncedFetch();
    });

    leftAmount?.addEventListener("blur", () => {
        let val = leftAmount.value.trim().replace(",", ".");
        if (!val || isNaN(parseFloat(val))) val = "1";
        leftAmount.value = val;
        debouncedFetch();
    });
}
