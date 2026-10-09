"""
Title: SMART-SIP+ techno-economic engine.

Chain:  parcel climate (GEE ERA5-Land) -> seasonal crop water balance (FAO-56 Kc,
        effective rain) -> design flow -> TDH -> pump kW -> PV kWp (power AND energy
        sized, cell-temperature derated) -> monthly energy balance -> savings,
        revenue, loan, NPV / IRR / LCOE -> groundwater safeguard screen.

All unit costs / prices below are PLACEHOLDER assumptions (BDT, ~2024). They are
overridable per run through SystemSpec; replace them with supplier quotes.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import calendar
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

# ── Unit costs & prices (BDT) — placeholders ─────────────────────────────────
PANEL_COST_PER_KWP = 85_000
INVERTER_COST_PER_KW = 12_000
STRUCTURE_COST_PER_KWP = 8_000
INSTALL_COST_PER_KWP = 5_000
BATTERY_COST_PER_KWH = 35_000
COLD_COST_PER_WATT = 25
EV_CHARGER_COST = 120_000
ERICKSHAW_BATT_COST = 45_000
DIESEL_PRICE_PER_LITRE = 110
DIESEL_LITRES_PER_KWH = 0.28       # litres per kWh of pump input energy
GRID_TARIFF_PER_KWH = 8.0
CO2_KG_PER_LITRE = 2.68
DISCOUNT_RATE = 0.08
PANEL_DEGRADATION = 0.005
OPEX_RATE = 0.015                  # of gross CAPEX per year
SYSTEM_LIFETIME = 25
INVERTER_LIFE_YEARS = 12           # one replacement inside the 25-yr horizon

# ── PV performance ───────────────────────────────────────────────────────────
DUST_LOSS, MISMATCH_LOSS, CABLE_LOSS = 0.04, 0.02, 0.01
SYSTEM_EFF = 1 - DUST_LOSS - MISMATCH_LOSS - CABLE_LOSS
INVERTER_EFF = 0.96
TEMP_COEFF = 0.004                 # power loss per °C of cell temp above 25 °C
CELL_TEMP_RISE = 20.0              # cell temp ≈ daytime air temp + 20 °C (ground mount)
DEFAULT_CELL_TEMP = 45.0
PV_OVERSIZE = 1.25                 # power-sizing margin
ENERGY_MARGIN = 1.05               # energy-sizing margin
SURPLUS_MONETISED = 0.30           # share of surplus kWh sold / used

# ── Add-on assumptions ───────────────────────────────────────────────────────
COLD_KG_PER_KW = 1000              # produce capacity per kW compressor
COLD_DUTY = 0.5                    # compressor duty cycle
COLD_UTILISATION = 0.7
COLD_FEE_BDT_KG_MONTH = 0.8
COLD_MONTHS_OCCUPIED = 6
COLD_SPOILAGE_BDT_KG_YR = 3.0
COLD_DAYLIGHT_SHARE = 0.6          # share of compressor load that can run in daylight
ERICKSHAW_CYCLES_PER_DAY = 3
ERICKSHAW_KWH_PER_CYCLE = 4.8      # 48 V / 100 Ah
ERICKSHAW_FEE_BDT_PER_KWH = 12.0
ERICKSHAW_OP_DAYS = 300

SUCTION_LIMIT_M = 7.0              # practical lift limit of a surface (suction) pump
KWH_PER_M3_M = 1000 * 9.81 / 3.6e6  # hydraulic kWh to lift 1 m³ by 1 m
DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], float)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Small physical helpers ───────────────────────────────────────────────────
def effective_rain(p_mm: float) -> float:
    """USDA-SCS monthly effective rainfall (FAO/AGLW)."""
    p = max(0.0, float(p_mm))
    return p * (125 - 0.2 * p) / 125 if p <= 250 else 125 + 0.1 * p


def cell_temperature(tmean_c, tmax_c):
    """Generation-weighted cell temperature from ERA5-Land daily air temperature."""
    return 0.5 * (np.asarray(tmean_c, float) + np.asarray(tmax_c, float)) + CELL_TEMP_RISE


def temp_derate(tcell_c):
    return 1 - TEMP_COEFF * np.maximum(0.0, np.asarray(tcell_c, float) - 25.0)


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class HydraulicSpec:
    flow_m3h: float
    tdh_m: float
    pump_efficiency: float
    power_kw: float = 0.0
    panel_kwp: float = 0.0


@dataclass
class SystemSpec:
    district: str
    crop_type: str
    area_ha: float
    pump_kw: float
    panel_kwp: float
    ghi_daily: float = 4.8             # legacy flat value, used only when clim is None
    temp_avg_c: float = 28.0           # legacy
    clim: dict | None = None           # monthly parcel climate (see utils.climate)
    planting_month: int = 12
    irr_eff: float = 0.60
    lat: float | None = None
    lon: float | None = None
    gw_depth_m: float = 5.0
    drawdown_m: float = 2.0
    pipe_friction_m: float = 2.0
    pump_efficiency: float = 0.60
    flow_m3h: float = 0.0
    irrigation_hours: float = 8.0
    subsidy_pct: float = 0.30
    financing_rate: float = 0.12
    loan_share: float = 0.0
    loan_years: int = 5
    cold_storage_w: float = 0.0
    cold_capacity_kg: float | None = None   # None -> COLD_KG_PER_KW * kW (placeholder)
    n_erickshaw_chargers: int = 0
    battery_kwh: float = 0.0
    ev_charger: bool = False
    diesel_price: float = DIESEL_PRICE_PER_LITRE
    grid_tariff: float = GRID_TARIFF_PER_KWH
    panel_cost_kwp: float = PANEL_COST_PER_KWP
    discount_rate: float = DISCOUNT_RATE
    ghi_factor: float = 1.0            # local calibration of ERA5-Land GHI
    recharge_frac: float = 0.20        # assumed net recharge as share of rainfall
    gw_trend: str = "unknown"          # declining | stable | unknown


@dataclass
class SystemResult:
    tdh_m: float
    flow_m3h: float
    pump_kw: float
    panel_kwp: float
    daily_generation_kwh: float
    daily_irrigation_kwh: float
    daily_surplus_kwh: float
    psh: float
    total_capex: float
    total_capex_after_subsidy: float
    annual_opex: float
    annual_diesel_cost_saved: float
    annual_cold_revenue: float
    annual_erickshaw_revenue: float
    annual_grid_income: float
    annual_grid_import_cost: float
    net_annual_saving: float
    payback_years: float
    npv_25yr: float
    irr: float
    lcoe_bdt_per_kwh: float
    lcoe_subsidised: float
    diesel_cost_per_kwh: float
    co2_tonnes_per_year: float
    diesel_litres_per_year: float
    water_vol_m3_per_day: float
    annual_volume_m3: float
    annual_irrigation_mm: float
    season_days: int
    solar_fraction: float
    peak_hours_needed: float
    landprep_days: float
    aquifer_risk: str
    aquifer_message: str
    safeguard: dict
    annual_debt_service: float
    equity_payback_years: float
    min_dscr: float
    climate_source: str
    ghi_mean: float
    tcell_mean: float
    monthly: pd.DataFrame
    components: pd.DataFrame
    cashflow: pd.DataFrame


# ── Hydraulics & sizing ──────────────────────────────────────────────────────
def compute_hydraulic(flow_m3h: float, gw_depth_m: float, drawdown_m: float = 2.0,
                      pipe_friction_m: float = 2.0, pump_efficiency: float = 0.60,
                      cell_temp_c: float = DEFAULT_CELL_TEMP) -> HydraulicSpec:
    """Pump kW = rho g Q H / eta ; kWp from power at peak sun with cell-temp derating."""
    tdh = gw_depth_m + drawdown_m + pipe_friction_m + 1.0       # +1 m delivery head
    power_kw = 9.81 * (flow_m3h / 3600.0) * tdh / pump_efficiency
    derate = float(temp_derate(cell_temp_c))
    panel_kwp = power_kw / (SYSTEM_EFF * INVERTER_EFF * derate) * PV_OVERSIZE
    return HydraulicSpec(round(flow_m3h, 2), round(tdh, 2), pump_efficiency,
                         round(power_kw, 3), round(panel_kwp, 3))


def seasonal_water_balance(crop: str, area_ha: float, planting_month: int, clim: dict,
                           irr_eff: float = 0.60, pump_hours: float = 8.0,
                           peak_factor: float = 1.10) -> dict:
    """
    Day-by-day crop water balance over the crop calendar.
    net irrigation = max(0, Kc*ETo + percolation - effective rain), per day.
    ETo and rainfall come from the parcel's ERA5-Land climatology.
    """
    from data.bangladesh_data import CROP_ETC
    info = CROP_ETC.get(crop, CROP_ETC["Boro Rice"])
    total = int(info["total_days"])
    kc_days = []
    for _, d, kc in info["stages"]:
        kc_days += [kc] * int(d)
    kc_days = (kc_days + [kc_days[-1]] * total)[:total]
    perc = float(info.get("perc_mm_day", 0.0))
    prep = float(info.get("landprep_mm", 0.0))
    eto = np.asarray(clim["eto"], float)
    peff = np.array([effective_rain(p) for p in clim["precip_mm"]])
    pm = int(planting_month) - 1

    net, etc_m, crop_days = np.zeros(12), np.zeros(12), np.zeros(12)
    d0 = date(2023, pm + 1, 1)
    for i in range(total):
        d = d0 + timedelta(days=i)
        m = d.month - 1
        dim = calendar.monthrange(d.year, d.month)[1]
        etc = kc_days[i] * eto[m]
        etc_m[m] += etc
        net[m] += max(0.0, etc + perc - peff[m] / dim)
        crop_days[m] += 1
    daily_mm = np.divide(net / irr_eff, crop_days, out=np.zeros(12), where=crop_days > 0)  # design basis: crop demand only
    prep_net = max(0.0, prep - peff[pm])                # land preparation (paddy): volume, not peak flow
    net[pm] += prep_net

    gross = net / irr_eff
    vol = gross * area_ha * 10.0                        # 1 mm over 1 ha = 10 m³
    landprep_m3 = prep_net / irr_eff * area_ha * 10.0
    peak_m3_day = float(daily_mm.max() * area_ha * 10.0 * peak_factor)
    return {
        "etc_mm": etc_m, "peff_mm": peff, "net_mm": net, "gross_mm": gross,
        "vol_m3": vol, "crop_days": crop_days, "daily_gross_mm": daily_mm, "landprep_m3": landprep_m3,
        "peak_month": int(daily_mm.argmax()), "peak_m3_day": peak_m3_day,
        "design_flow_m3h": peak_m3_day / max(pump_hours, 1e-6),
        "annual_vol_m3": float(vol.sum()), "annual_gross_mm": float(gross.sum()),
        "season_days": total,
    }


def auto_design(crop, area_ha, planting_month, clim, gw_depth_m, drawdown_m=2.0,
                pipe_friction_m=2.0, pump_efficiency=0.60, irr_eff=0.60,
                pump_hours=8.0, ghi_factor=1.0):
    """ETc -> flow -> TDH -> kW -> kWp. kWp = max(power-based, monthly-energy-based)."""
    wb = seasonal_water_balance(crop, area_ha, planting_month, clim, irr_eff, pump_hours)
    tc = cell_temperature(clim["tmean"], clim["tmax"])
    hyd = compute_hydraulic(wb["design_flow_m3h"], gw_depth_m, drawdown_m,
                            pipe_friction_m, pump_efficiency, float(tc[wb["peak_month"]]))
    tdh = hyd.tdh_m
    e_pump_day = np.divide(wb["vol_m3"] * tdh * KWH_PER_M3_M / pump_efficiency, DAYS)
    e_pump_day = np.minimum(e_pump_day, hyd.power_kw * pump_hours)       # pump capacity cap
    pv_per_kwp = (np.asarray(clim["ghi"]) * ghi_factor * temp_derate(tc) * SYSTEM_EFF * INVERTER_EFF)
    active = wb["vol_m3"] > 0
    kwp_energy = float(np.max(np.where(active, e_pump_day / np.maximum(pv_per_kwp, 1e-6), 0))) * ENERGY_MARGIN
    hyd.panel_kwp = round(max(hyd.panel_kwp, kwp_energy), 3)
    return wb, hyd


# ── Groundwater safeguard screen ─────────────────────────────────────────────
def groundwater_safeguard(gw_depth_m, drawdown_m, annual_gross_mm, annual_precip_mm,
                          recharge_frac=0.20, gw_trend="unknown") -> dict:
    """
    Transparent screening index (NOT a hydrogeological assessment).
      * lift vs the practical suction-pump limit            (physics)
      * irrigation depth vs assumed recharge = frac * rain   (screening ratio)
      * user-declared water-table trend
    """
    lift = gw_depth_m + drawdown_m
    ratio = annual_gross_mm / max(annual_precip_mm * recharge_frac, 1.0)
    msgs, score = [], 0
    if lift > SUCTION_LIMIT_M:
        score += 1
        msgs.append(f"Pumping lift {lift:.1f} m exceeds the ~{SUCTION_LIMIT_M:.0f} m suction limit - "
                    "a submersible / deep-set pump is required (cost and kW rise).")
    if ratio > 1.5:
        score += 2 if ratio > 3.0 else 1
        msgs.append(f"Irrigation depth {annual_gross_mm:,.0f} mm/yr is {ratio:.1f}x the assumed recharge "
                    f"({recharge_frac:.0%} of {annual_precip_mm:,.0f} mm rain). Screening flag for "
                    "over-extraction: consider water-saving irrigation or a less thirsty crop.")
    elif ratio > 0.8:
        score += 1
        msgs.append(f"Irrigation depth is {ratio:.1f}x assumed recharge - monitor the water table.")
    if gw_trend == "declining":
        score += 1
        msgs.append("Water table is declining at this site - new abstraction needs permit review.")
    level = "High" if score >= 3 else "Medium" if score >= 1 else "Low"
    if not msgs:
        msgs.append("No groundwater flags from lift, extraction ratio or trend (screening only).")
    return {"level": level, "score": score, "messages": msgs,
            "extraction_ratio": ratio, "lift_m": lift}


# ── Finance helpers ──────────────────────────────────────────────────────────
def _irr(cfs: list) -> float:
    """IRR by bisection on [-0.9, 5]; 0.0 if there is no sign change."""
    f = lambda r: sum(c / (1 + r) ** t for t, c in enumerate(cfs))
    lo, hi = -0.9, 5.0
    if f(lo) * f(hi) > 0:
        return 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return round((lo + hi) / 2, 4)


def _fallback_clim(spec) -> dict:
    """Flat climate from legacy scalars; only used when no parcel climate is supplied."""
    return {"source": "flat_legacy", "ghi": [spec.ghi_daily] * 12, "tmean": [spec.temp_avg_c] * 12,
            "tmax": [spec.temp_avg_c + 5] * 12, "tmin": [spec.temp_avg_c - 5] * 12,
            "precip_mm": [100.0] * 12, "eto": [4.0] * 12}


# ── Main system model ────────────────────────────────────────────────────────
def size_system(spec: SystemSpec) -> SystemResult:
    clim = spec.clim or _fallback_clim(spec)
    ghi = np.asarray(clim["ghi"], float) * spec.ghi_factor
    tcell = cell_temperature(clim["tmean"], clim["tmax"])
    derate = temp_derate(tcell)

    tdh = spec.gw_depth_m + spec.drawdown_m + spec.pipe_friction_m + 1.0
    eff = spec.pump_efficiency
    wb = seasonal_water_balance(spec.crop_type, spec.area_ha, spec.planting_month, clim,
                                spec.irr_eff, spec.irrigation_hours)

    # monthly energy balance
    e_pump = wb["vol_m3"] * tdh * KWH_PER_M3_M / eff                      # kWh / month
    gen_day = spec.panel_kwp * ghi * derate * SYSTEM_EFF * INVERTER_EFF
    gen_m = gen_day * DAYS
    pump_solar = np.minimum(e_pump, gen_m)
    surplus = np.maximum(0.0, gen_m - e_pump)
    flow_cap = spec.pump_kw * eff * 3600 / (9.81 * tdh)                    # m³/h at rated kW
    hrs_needed = float(np.max(np.divide(wb["daily_gross_mm"] * spec.area_ha * 10 * 1.10,
                                        max(flow_cap, 1e-6))))

    landprep_days = float(wb["landprep_m3"] / max(flow_cap * spec.irrigation_hours, 1e-6))

    # add-on loads served from the surplus
    cold_kw = spec.cold_storage_w / 1000.0
    cold_need = cold_kw * 24 * COLD_DUTY * DAYS
    cold_kwh_day = max(cold_kw * 24 * COLD_DUTY, 1e-6)
    solar_share = min(1.0, COLD_DAYLIGHT_SHARE + spec.battery_kwh / cold_kwh_day) if cold_kw else 0.0
    cold_served = np.minimum(surplus, cold_need * solar_share)
    surplus_after_cold = surplus - cold_served
    er_need = (spec.n_erickshaw_chargers * ERICKSHAW_CYCLES_PER_DAY * ERICKSHAW_KWH_PER_CYCLE
               * ERICKSHAW_OP_DAYS / 365.0) * DAYS
    er_served = np.minimum(surplus_after_cold, er_need)
    surplus_free = surplus_after_cold - er_served

    # annual benefits (BDT)
    diesel_l = float(pump_solar.sum() * DIESEL_LITRES_PER_KWH)
    diesel_saved = diesel_l * spec.diesel_price
    cold_cap_kg = spec.cold_capacity_kg if spec.cold_capacity_kg is not None else cold_kw * COLD_KG_PER_KW
    cold_rev = cold_cap_kg * COLD_UTILISATION * (COLD_FEE_BDT_KG_MONTH * COLD_MONTHS_OCCUPIED
                                                 + COLD_SPOILAGE_BDT_KG_YR) if cold_kw else 0.0
    grid_import_cost = float((cold_need - cold_served).sum() * spec.grid_tariff) if cold_kw else 0.0
    er_rev = float(er_served.sum() * ERICKSHAW_FEE_BDT_PER_KWH)
    grid_income = float(surplus_free.sum() * spec.grid_tariff * SURPLUS_MONETISED)

    # CAPEX
    panel_cost = spec.panel_kwp * spec.panel_cost_kwp
    inverter_cost = spec.pump_kw * INVERTER_COST_PER_KW
    struct_cost = spec.panel_kwp * STRUCTURE_COST_PER_KWP
    install_cost = spec.panel_kwp * INSTALL_COST_PER_KWP
    battery_cost = spec.battery_kwh * BATTERY_COST_PER_KWH
    cold_cost = spec.cold_storage_w * COLD_COST_PER_WATT
    er_cost = spec.n_erickshaw_chargers * ERICKSHAW_BATT_COST
    ev_cost = EV_CHARGER_COST if spec.ev_charger else 0
    capex = panel_cost + inverter_cost + struct_cost + install_cost + battery_cost + cold_cost + er_cost + ev_cost
    capex_net = capex * (1 - spec.subsidy_pct)

    opex = capex * OPEX_RATE + grid_import_cost                 # O&M on real hardware cost
    benefits = diesel_saved + cold_rev + er_rev + grid_income
    net_saving = benefits - opex
    payback = capex_net / net_saving if net_saving > 0 else 999.0

    # 25-year cash flow (unlevered) with degradation and one inverter replacement
    rows, cum, cfs = [], -capex_net, [-capex_net]
    for y in range(1, SYSTEM_LIFETIME + 1):
        cf = benefits * (1 - PANEL_DEGRADATION) ** (y - 1) - opex
        if y == INVERTER_LIFE_YEARS:
            cf -= inverter_cost
        cum += cf
        cfs.append(cf)
        rows.append({"year": y, "net_saving": cf, "pv_saving": cf / (1 + spec.discount_rate) ** y,
                     "cumulative": cum})
    cf_df = pd.DataFrame(rows)
    npv = float(cf_df["pv_saving"].sum() - capex_net)
    irr = _irr(cfs)

    # LCOE: PV system cost / discounted energy generated
    gen_year = float(gen_m.sum())
    disc_energy = sum(gen_year * (1 - PANEL_DEGRADATION) ** (y - 1) / (1 + spec.discount_rate) ** y
                      for y in range(1, SYSTEM_LIFETIME + 1))
    pv_om = sum(capex * OPEX_RATE / (1 + spec.discount_rate) ** y for y in range(1, SYSTEM_LIFETIME + 1))
    pv_inv = inverter_cost / (1 + spec.discount_rate) ** INVERTER_LIFE_YEARS
    lcoe = (capex + pv_om + pv_inv) / disc_energy if disc_energy > 0 else 0.0
    lcoe_sub = (capex_net + pv_om + pv_inv) / disc_energy if disc_energy > 0 else 0.0

    # loan / equity view
    principal = capex_net * spec.loan_share
    r, n = spec.financing_rate, int(spec.loan_years)
    pmt = principal * r / (1 - (1 + r) ** -n) if principal > 0 and r > 0 else (principal / n if principal > 0 else 0.0)
    equity = capex_net - principal
    eq_cum, eq_pb, dscr = -equity, 999.0, []
    for y in range(1, SYSTEM_LIFETIME + 1):
        cf = cfs[y]
        ds = pmt if y <= n else 0.0
        if ds > 0:
            dscr.append((cf + 0.0) / ds)
        prev = eq_cum
        eq_cum += cf - ds
        if eq_pb == 999.0 and eq_cum >= 0:
            eq_pb = (y - 1) + (-prev / (eq_cum - prev) if eq_cum != prev else 0)
    min_dscr = float(min(dscr)) if dscr else 0.0

    # groundwater safeguard
    sg = groundwater_safeguard(spec.gw_depth_m, spec.drawdown_m, wb["annual_gross_mm"],
                               float(np.sum(clim["precip_mm"])), spec.recharge_frac, spec.gw_trend)

    # monthly table
    monthly = pd.DataFrame({
        "Month": MONTHS, "GHI kWh/m²/d": ghi.round(2), "T cell °C": tcell.round(1),
        "ETo mm/d": np.round(clim["eto"], 2), "Rain mm": np.round(clim["precip_mm"], 0),
        "Eff. rain mm": wb["peff_mm"].round(0), "ETc mm": wb["etc_mm"].round(0),
        "Gross irrig. mm": wb["gross_mm"].round(0), "Volume m³": wb["vol_m3"].round(0),
        "Pump kWh": e_pump.round(0), "PV kWh": gen_m.round(0),
        "Solar-pumped kWh": pump_solar.round(0), "Surplus kWh": surplus.round(0),
    })

    comp = [
        {"Component": "Solar Panels", "Specification": f"{spec.panel_kwp:.2f} kWp ({int(math.ceil(spec.panel_kwp / 0.45))} x 450 W)",
         "Unit Cost (BDT)": f"৳{spec.panel_cost_kwp:,.0f}/kWp", "Total (BDT)": int(panel_cost)},
        {"Component": "Pump Inverter (MPPT)", "Specification": f"{spec.pump_kw:.2f} kW VFD drive",
         "Unit Cost (BDT)": f"৳{INVERTER_COST_PER_KW:,}/kW", "Total (BDT)": int(inverter_cost)},
        {"Component": "Mounting Structure", "Specification": "Ground-mount galvanised steel",
         "Unit Cost (BDT)": f"৳{STRUCTURE_COST_PER_KWP:,}/kWp", "Total (BDT)": int(struct_cost)},
        {"Component": "Installation & Wiring", "Specification": "Labour, DC/AC cabling, commissioning",
         "Unit Cost (BDT)": f"৳{INSTALL_COST_PER_KWP:,}/kWp", "Total (BDT)": int(install_cost)},
    ]
    if spec.battery_kwh > 0:
        comp.append({"Component": "Battery Storage", "Specification": f"{spec.battery_kwh} kWh Li-ion",
                     "Unit Cost (BDT)": f"৳{BATTERY_COST_PER_KWH:,}/kWh", "Total (BDT)": int(battery_cost)})
    if spec.cold_storage_w > 0:
        comp.append({"Component": "Cold Storage Unit", "Specification": f"{spec.cold_storage_w:.0f} W compressor, ~{cold_cap_kg:,.0f} kg",
                     "Unit Cost (BDT)": f"৳{COLD_COST_PER_WATT}/W", "Total (BDT)": int(cold_cost)})
    if spec.n_erickshaw_chargers > 0:
        comp.append({"Component": "E-Rickshaw Charging Hub", "Specification": f"{spec.n_erickshaw_chargers} x 48V/100Ah points",
                     "Unit Cost (BDT)": f"৳{ERICKSHAW_BATT_COST:,}/point", "Total (BDT)": int(er_cost)})
    if spec.ev_charger:
        comp.append({"Component": "EV Charging Point (Type-2)", "Specification": "3.3 kW AC charger",
                     "Unit Cost (BDT)": f"৳{EV_CHARGER_COST:,}", "Total (BDT)": int(ev_cost)})
    comp.append({"Component": "TOTAL (before subsidy)", "Specification": "", "Unit Cost (BDT)": "", "Total (BDT)": int(capex)})
    comp.append({"Component": f"After {spec.subsidy_pct * 100:.0f}% Subsidy", "Specification": "", "Unit Cost (BDT)": "", "Total (BDT)": int(capex_net)})

    solar_frac = float(pump_solar.sum() / e_pump.sum()) if e_pump.sum() > 0 else 0.0
    return SystemResult(
        tdh_m=tdh, flow_m3h=wb["design_flow_m3h"], pump_kw=spec.pump_kw, panel_kwp=spec.panel_kwp,
        daily_generation_kwh=gen_year / 365.0, daily_irrigation_kwh=float(e_pump.sum() / 365.0),
        daily_surplus_kwh=float(surplus.sum() / 365.0),
        psh=float(np.average(ghi * derate, weights=DAYS)),
        total_capex=capex, total_capex_after_subsidy=capex_net, annual_opex=opex,
        annual_diesel_cost_saved=diesel_saved, annual_cold_revenue=cold_rev,
        annual_erickshaw_revenue=er_rev, annual_grid_income=grid_income,
        annual_grid_import_cost=grid_import_cost, net_annual_saving=net_saving,
        payback_years=round(payback, 1), npv_25yr=round(npv), irr=irr,
        lcoe_bdt_per_kwh=round(lcoe, 2), lcoe_subsidised=round(lcoe_sub, 2),
        diesel_cost_per_kwh=round(DIESEL_LITRES_PER_KWH * spec.diesel_price, 2),
        co2_tonnes_per_year=round(diesel_l * CO2_KG_PER_LITRE / 1000, 3),
        diesel_litres_per_year=round(diesel_l), water_vol_m3_per_day=wb["peak_m3_day"],
        annual_volume_m3=wb["annual_vol_m3"], annual_irrigation_mm=wb["annual_gross_mm"],
        season_days=wb["season_days"], solar_fraction=solar_frac, peak_hours_needed=hrs_needed,
        landprep_days=landprep_days,
        aquifer_risk=sg["level"], aquifer_message=" ".join(sg["messages"]), safeguard=sg,
        annual_debt_service=pmt, equity_payback_years=round(eq_pb, 1), min_dscr=min_dscr,
        climate_source=clim.get("source", "unknown"), ghi_mean=float(np.average(ghi, weights=DAYS)),
        tcell_mean=float(np.average(tcell, weights=DAYS)),
        monthly=monthly, components=pd.DataFrame(comp), cashflow=cf_df,
    )


# ── National scenario ────────────────────────────────────────────────────────
def reference_system_cost(avg_pump_kw: float = 3.7) -> float:
    """Gross cost (BDT) of an average system, from the same unit costs as size_system."""
    kwp = avg_pump_kw / (SYSTEM_EFF * INVERTER_EFF * float(temp_derate(DEFAULT_CELL_TEMP))) * PV_OVERSIZE
    return kwp * (PANEL_COST_PER_KWP + STRUCTURE_COST_PER_KWP + INSTALL_COST_PER_KWP) \
        + avg_pump_kw * INVERTER_COST_PER_KW


def run_national_scenario(target_year: int, replacement_rate_pct: float, subsidy_pct: float,
                          cold_integration_pct: float, ev_adoption_pct: float,
                          total_pumps: int = 3_400_000, base_year: int = 2025,
                          avg_pump_kw: float = 3.7, hours_per_day: float = 8.0,
                          days_per_year: float = 120.0, unit_cost_bdt: float | None = None) -> dict:
    """
    National roll-out arithmetic. Every driver is an explicit argument: the baseline
    is derived from the SAME per-pump assumptions, so CO2 saved can never exceed it.
    """
    unit_cost = unit_cost_bdt or reference_system_cost(avg_pump_kw)
    diesel_l_pump = avg_pump_kw * hours_per_day * days_per_year * DIESEL_LITRES_PER_KWH
    co2_t_pump = diesel_l_pump * CO2_KG_PER_LITRE / 1000
    years = list(range(base_year, target_year + 1))
    rate = replacement_rate_pct / 100
    out = {k: [] for k in ["replaced_cumulative", "co2_saved_mt", "diesel_saved_gl", "investment_bdt_bn",
                           "subsidy_cost_bdt_bn", "cold_storage_nodes", "ev_charging_points", "adoption_pct"]}
    for yr in years:
        cum = min(total_pumps, total_pumps * (1 - (1 - rate) ** (yr - base_year)))
        out["replaced_cumulative"].append(cum)
        out["co2_saved_mt"].append(cum * co2_t_pump / 1e6)
        out["diesel_saved_gl"].append(cum * diesel_l_pump / 1e9)
        out["investment_bdt_bn"].append(cum * unit_cost * (1 - subsidy_pct / 100) / 1e9)
        out["subsidy_cost_bdt_bn"].append(cum * unit_cost * (subsidy_pct / 100) / 1e9)
        out["cold_storage_nodes"].append(cum * cold_integration_pct / 100)
        out["ev_charging_points"].append(cum * ev_adoption_pct / 100)
        out["adoption_pct"].append(cum / total_pumps * 100)
    out.update(years=years, baseline_co2_mt=total_pumps * co2_t_pump / 1e6,
               baseline_diesel_gl=total_pumps * diesel_l_pump / 1e9,
               unit_cost_bdt=unit_cost, co2_t_per_pump=co2_t_pump, diesel_l_per_pump=diesel_l_pump)
    return out
