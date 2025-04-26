/** @odoo-module **/

import { registry } from "@web/core/registry";
import { deserializeDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

export const OfferTimerService = {
    start() {
        return {
            create(params) {
                if (params.offerDate !== undefined && params.offerDate !== 'false') {
                    let offerTime = deserializeDateTime(params.offerDate);
                    let currentTime = DateTime.now();
                    let duration = offerTime.ts - currentTime.ts;
                    if (duration < 0) {
                        let storedTimerInfo = sessionStorage.getItem("as_timer_ids");
                        if (storedTimerInfo) {
                            let storedTimerIds = JSON.parse(storedTimerInfo);
                            storedTimerIds.forEach(intervalId => {
                                clearInterval(intervalId);
                            });
                        }
                        sessionStorage.removeItem("as_timer_ids");
                        params.target.empty();
                    } else {
                        let days = Math.floor(duration / (1000 * 60 * 60 * 24));
                        let hours = Math.floor((duration / (1000 * 60 * 60)) % 24);
                        let minutes = Math.floor((duration / 1000 / 60) % 60);
                        let seconds = Math.floor((duration / 1000) % 60);
                        days = days < 10 ? "0" + days : days;
                        hours = hours < 10 ? "0" + hours : hours;
                        minutes = minutes < 10 ? "0" + minutes : minutes;
                        seconds = seconds < 10 ? "0" + seconds : seconds;
                        params.target.removeClass("d-none");
                        params.target.html(`
                            <ul>
                                <li><label>${days}</label><span>Days</span></li>
                                <li><label>${hours}</label><span>Hours</span></li>
                                <li><label>${minutes}</label><span>Minutes</span></li>
                                <li><label>${seconds}</label><span>Seconds</span></li>
                            </ul>
                        `);
                    }
                }
            }
        }
    },

};
registry.category("services").add("offer_timer", OfferTimerService);