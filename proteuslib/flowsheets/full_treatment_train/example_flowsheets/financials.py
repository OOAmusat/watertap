###############################################################################
# ProteusLib Copyright (c) 2021, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National
# Laboratory, National Renewable Energy Laboratory, and National Energy
# Technology Laboratory (subject to receipt of any required approvals from
# the U.S. Dept. of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/nawi-hub/proteuslib/"
#
###############################################################################
from pyomo.environ import (
    Block, Constraint, Expression, Var, Param, Reals, NonNegativeReals, units as pyunits)
from idaes.core.util.exceptions import ConfigurationError
pyunits.load_definitions_from_strings(['USD = [currency]'])
pyunits.USD # dollars


# TODO: choose year --> 2018 probably (use CEPCI)
#  mixers, splitters, pumps, erds, RO, NF, stoich reactor (lime softening), equilibrium reactor (chlorination)

def add_costing_param_block(self):
    self.costing_param = Block()
    b = self.costing_param

    b.load_factor = Var(
        initialize=0.9,
        doc='Load factor [fraction of uptime]')
    b.factor_total_investment = Var(
        initialize=2,
        doc='Total investment factor [investment cost/equipment cost]')
    b.factor_labor_maintenance = Var(
        initialize=0.02,
        doc='Labor & maintenance factor [fraction of investment cost/year]')
    b.factor_capital_annualization = Var(
        initialize=0.1,
        doc='Capital annualization factor [fraction of investment cost/year]')
    b.factor_membrane_replacement = Var(
        initialize=0.2,
        doc='Membrane replacement factor [fraction of membrane replaced/year]')
    b.electricity_cost = Var(
        initialize=0.07,
        doc='Electricity cost [$/kWh]')
    b.RO_mem_cost = Var(
        initialize=30*3, #increase to cost representative of ultra-high pressure ro membrane
        doc='Membrane cost [$/m2]')
    b.NF_mem_cost = Var(
        initialize=15,  # assumed as half that of conventional SWRO membrane
        doc='Membrane cost [$/m2]')
    b.hp_pump_cost = Var(
        initialize=53 / 1e5 * 3600,
        doc='High pressure pump cost [$/W]')
    b.pxr_cost = Var(
        initialize=535,
        doc='Pressure exchanger cost [$/(m3/h)]')

    # traditional parameters are the only Vars on the block and should be fixed
    for v in b.component_objects(Var, descend_into=True):
        for i in v:
            if v[i].value is None:
                raise ConfigurationError(
                    "{} parameter {} was not assigned"
                    " a value. Please check your configuration "
                    "arguments.".format(b.name, v.local_name))
            v[i].fix()


def get_system_costing(self):
    if not hasattr(self, 'costing'):
        self.costing = Block()
    b = self.costing

    b.capital_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total capital cost [$]')
    b.investment_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total investment cost [$]')
    b.operating_cost_labor_maintenance = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Maintenance-labor-chemical operating cost [$/year]')
    b.operating_cost_total = Var(
        initialize=1e3,
        domain=NonNegativeReals,
        doc='Total operating cost [$/year]')
    b.LCOW = Var(
        initialize=1,
        domain=NonNegativeReals,
        doc='Levelized cost of water [$/m3]')

    capital_cost_var_lst = []
    operating_cost_var_lst = []
    electricity_cost_var_lst = []
    pretreatment_cost_var_lst = []
    primary_cost_var_lst = []
    post_treatment_cost_var_lst = []
    for b_unit in self.component_objects(Block, descend_into=True):
        if hasattr(b_unit, 'costing'):
            capital_cost_var_lst.append(b_unit.costing.capital_cost)
            operating_cost_var_lst.append(b_unit.costing.operating_cost)
            if hasattr(b_unit.costing, 'pretreatment'):
                pretreatment_cost_var_lst.append(b_unit.costing.pretreatment)
            if hasattr(b_unit.costing, 'primary'):
                primary_cost_var_lst.append(b_unit.costing.primary)
            if hasattr(b_unit.costing, 'post_treatment'):
                post_treatment_cost_var_lst.append(b_unit.costing.post_treatment)
            if 'electricity_cost' in str(b_unit.costing.eq_operating_cost.body):
                electricity_cost_var_lst.append(b_unit.costing.operating_cost)
    operating_cost_var_lst.append(b.operating_cost_labor_maintenance)

    b.eq_capital_cost_total = Constraint(
        expr=b.capital_cost_total == sum(capital_cost_var_lst))
    b.eq_investment_cost_total = Constraint(
        expr=(b.investment_cost_total ==
              b.capital_cost_total * self.costing_param.factor_total_investment))
    b.eq_operating_cost_labor_maintenance = Constraint(
        expr=(b.operating_cost_labor_maintenance ==
              b.investment_cost_total * self.costing_param.factor_labor_maintenance))
    b.eq_operating_cost_total = Constraint(
        expr=b.operating_cost_total == sum(operating_cost_var_lst))
    b.electricity_cost_total = Expression(
        expr=sum(electricity_cost_var_lst))
    b.pretreatment_cost_total = Expression(
        expr= sum(pretreatment_cost_var_lst))
    b.primary_cost_total = Expression(
        expr=sum(primary_cost_var_lst))
    b.post_treatment_cost_total = Expression(
        expr=sum(post_treatment_cost_var_lst))
    b.eq_LCOW = Constraint(
        expr=b.LCOW == (b.investment_cost_total * self.costing_param.factor_capital_annualization
                        + b.operating_cost_total) / (self.annual_water_production / (pyunits.m ** 3 / pyunits.year)))


def _make_vars(self, section=None):
    # build generic costing variables (all costing models need these vars)
    self.capital_cost = Var(initialize=1e5,
                            domain=NonNegativeReals,
                            doc='Unit capital cost [$]')
    self.operating_cost = Var(initialize=1e5,
                              domain=Reals,
                              bounds=(0, 1e6),
                              doc='Unit operating cost [$/year]')
    if section not in ['pretreatment', 'primary', 'post_treatment']:
        raise NotImplementedError
    else:
        setattr(self, section, Expression(expr=self.capital_cost + self.operating_cost))

    self.cost_esc = Param(initialize=1, mutable=True, units=pyunits.dimensionless)


def ReverseOsmosis_costing(self, section='primary'):
    _make_vars(self, section)

    b_RO = self.parent_block()
    b_fs = b_RO.parent_block()
    # b_section = getattr(self, section)

    # capital cost
    self.eq_capital_cost = Constraint(
        expr=self.capital_cost == b_fs.costing_param.RO_mem_cost * b_RO.area / pyunits.m ** 2)

    # operating cost
    self.eq_operating_cost = Constraint(
        expr=self.operating_cost == b_fs.costing_param.factor_membrane_replacement
             * b_fs.costing_param.RO_mem_cost * b_RO.area / pyunits.m ** 2)

    # # Treatment section cost
    # self.eq_section = Constraint(expr=b_section == self.operating_cost + self.capital_cost)



def Nanofiltration_costing(self, section='pretreatment'):
    ''' This method is being added for the nanofiltration step in the pre-treatment section of the full treatment train'''

    _make_vars(self, section)

    b_NF = self.parent_block()
    b_fs = b_NF.parent_block()
    # b_section = getattr(self, section)

    # capital cost
    self.eq_capital_cost = Constraint(
        expr=self.capital_cost == b_fs.costing_param.NF_mem_cost * b_NF.area / pyunits.m ** 2)

    # operating cost
    self.eq_operating_cost = Constraint(
        expr=self.operating_cost == b_fs.costing_param.factor_membrane_replacement
             * b_fs.costing_param.NF_mem_cost * b_NF.area / pyunits.m ** 2)

    # # Treatment section cost
    # self.eq_section = Constraint(expr=b_section == self.operating_cost + self.capital_cost)

def Separator_costing(self, section=None, cost_capacity=False):
    _make_vars(self, section)

    b_m = self.parent_block()

    if cost_capacity:
        self.a = Param(initialize=645, mutable=True, units=pyunits.dimensionless)
        self.b = Param(initialize=1324, mutable=True, units=pyunits.dimensionless)
        self.n = Param(initialize=0.4, mutable=True, units=pyunits.dimensionless)
        # TODO: reconsider material factor=9 for converting cost of carbon steel to titanium
        self.Fm = Param(initialize=9, mutable=True, units=pyunits.dimensionless)

        # capital cost
        self.eq_capital_cost = Constraint(
            expr=self.capital_cost == (self.a
                                       + self.b
                                       * (b_m.outlet_state[0].flow_vol * 1000) ** self.n) * self.Fm
                 * self.cost_esc / (pyunits.m ** 3 / pyunits.s))
    elif not cost_capacity:
        # assume fixed cost per L/s based on average of cost capacity curve data
        self.mixer_unit_capex = Param(initialize=2165.3, mutable=True, units=pyunits.dimensionless,
                                      doc="Capex per daily plant capacity")
        self.eq_capital_cost = Constraint(expr=self.capital_cost == self.mixer_unit_capex
                                               * b_m.outlet_state[0].flow_vol * 1000 * self.cost_esc
                                               * pyunits.s * pyunits.m ** -3)

    self.operating_cost.fix(0)


def Mixer_costing(self, mixer_type='default', section=None, cost_capacity=False): #TODO add fixed cost options vs economies_of_scale
    _make_vars(self, section)

    b_m = self.parent_block()
    b_fs = b_m.parent_block()
    # b_section = getattr(self, section)

    if mixer_type == 'default':
        if cost_capacity:
            self.a = Param(initialize=645, mutable=True, units=pyunits.dimensionless)
            self.b = Param(initialize=1324, mutable=True, units=pyunits.dimensionless)
            self.n = Param(initialize=0.4, mutable=True, units=pyunits.dimensionless)
            # TODO: reconsider material factor=9 for converting cost of carbon steel to titanium
            self.Fm = Param(initialize=9, mutable=True, units=pyunits.dimensionless)

            # capital cost
            self.eq_capital_cost = Constraint(
                expr=self.capital_cost == (self.a
                                           + self.b
                                           * (b_m.outlet_state[0].flow_vol*1000) ** self.n) * self.Fm
                                           * self.cost_esc / (pyunits.m**3/pyunits.s))
        elif not cost_capacity:
            # assume fixed cost per L/s based on average of cost capacity curve data
            self.mixer_unit_capex = Param(initialize=2165.3, mutable=True, units=pyunits.dimensionless, doc="Capex per daily plant capacity")
            self.eq_capital_cost = Constraint(expr=self.capital_cost == self.mixer_unit_capex
                                              * b_m.outlet_state[0].flow_vol*1000 * self.cost_esc
                                                   * pyunits.s * pyunits.m**-3)

        self.operating_cost.fix(0)

    elif mixer_type == 'naocl_mixer':
        if cost_capacity:
            '''Cost estimation of chlorination step for disinfection in post-treatment
            Digitized Fig. 4.19 in Voutchkov, 2018 using WebPlotDigitizer, https://apps.automeris.io/wpd/,
             September 2021. Fig. 4.19 provides construction cost as a function of daily desalination plant capacity.
             Curves for sodium hypochlorite and chlorine dioxide are provided, but only NaOCl data were extracted.
             Data were converted to specific construction costs as a function of capacity to get the provided cost curve
             for capex (of the form a*X**b).
             Since cost figures are reported for the year 2018, the capex cost constraint is assumed to be in 2018 USD;the 
             cost escalation factor, cost_esc, can be modified to account for changes over time.'''

            # NaOCl specific capex ($/m3/day) = 479.87 * x ** (-0.396) ; x is plant capacity (m3/day)
            # TODO: may need to touch flow_vol while building naocl_mixer_unit. Double-check. Alternative: use flow_vol of RO final permeate
            self.eq_capital_cost = Constraint(expr=self.capital_cost ==
                                                   479.87
                                                   * (b_m.inlet_stream_state[0].flow_vol
                                                      * 3600 * 24 / (pyunits.m**3 / pyunits.s)) ** 0.604
                                                   * self.cost_esc)
        elif not cost_capacity:
            # assume fixed cost per daily capacity based on average of digitized data cited above
            self.naocl_unit_capex = Param(initialize=7.08, mutable=True, units=pyunits.day * pyunits.m**-3, doc="Capex per daily plant capacity")
            self.eq_capital_cost = Constraint(expr=self.capital_cost == self.naocl_unit_capex
                                              * b_m.inlet_stream_state[0].flow_vol*3600*24 * self.cost_esc
                                                   * pyunits.s * pyunits.day**-1)

        # Sodium hypochlorite cost taken from WaterTAP (2020 USD) which assumes 15% purity
        self.naocl_cost = Param(initialize=0.23, mutable=True, units=pyunits.kg**-1)
        self.naocl_purity = Param(initialize=0.15, mutable=True)
        #TODO: no electricity cost included -- would be based on pump work, expected to be negligible for the time being
        self.eq_operating_cost = Constraint(expr=self.operating_cost ==
                                                 b_m.naocl_stream.flow_mol[0]
                                                 * b_m.naocl_stream.mole_frac_comp[0, "OCl_-"]
                                                 * 74.44e-3 * pyunits.kg / pyunits.mol
                                                 * self.naocl_cost
                                                 / self.naocl_purity
                                                 * 3600 * 8760 * pyunits.s)

    elif mixer_type == 'lime_softening':
        '''Cost estimation of lime addition for precipitation step in pretreatment
        Digitized Fig. 5.59 in McGivney & Kawamura, 2008 using WebPlotDigitizer, https://apps.automeris.io/wpd/,
         September 2021. WaterTAP provides a similar equation for cost capacity curve based on the same reference.
         This is suspected to be due to digitization of the reference data although WaterTAP's documentation indicates that
         cost indices were accounted for. The original reference cites an ENR CCI = 8889, representative of the construction cost index 
         for Los Angeles in April 2007. Since recent year data for ENR's CCI are currently unknown, WaterTAP's equation will
         be used; note that WT's documentation may need to correct reporting of units/methodology.
         ------------------------------------------------------------------------------------------
         Cost capacity equations to consider:
         McGivney & Kawamura: 
         12985*x**0.5901
         =====================================================
         WaterTAP:
         16972*x**0.5435
         =====================================================
         Manual digitization and fitting relationships to original reference:
         1) Power law fit (coefficient of determination = 0.9721)
         13310*x**0.5855 
         2) Polynomial fit (coefficient of determination = 1)
         -1.4071*x**2 + 1661.9*x + 40782
         Although the polynomial fit matches the data more closely than other relationships, going above ~ 700 lb/day would 
         result in erroneous decrease in cost.
         '''
        # x is converts mol/s to lb/day
        self.lime_lbs_per_day = Expression(expr=2.205 * 3600 * 24 * 74.09e-3
                                                * b_m.lime_stream.flow_mol[0].value
                                                * b_m.lime_stream.mole_frac_comp[
                                                    0, "Ca(OH)2"].value / pyunits.mol * pyunits.s)
        if cost_capacity:
            self.eq_capital_cost = Constraint(expr=self.capital_cost == 16972 * self.lime_lbs_per_day ** 0.5435 * self.cost_esc)
        elif not cost_capacity:
            # assume fixed cost per lb feed per day based on average of digitized data cited above
            self.caoh2_unit_capex = Param(initialize=2133.5, mutable=True, units=pyunits.dimensionless, doc="Capex per lb feed per day")
            self.eq_capital_cost = Constraint(expr=self.capital_cost == self.caoh2_unit_capex
                                                   * self.lime_lbs_per_day * self.cost_esc)
        # Calcium hydroxide (lime) cost taken from WaterTAP (2020 USD) which assumes 100% purity
        self.caoh2_cost = Param(initialize=0.15, mutable=True, units=pyunits.kg**-1)
        self.caoh2_purity = Param(initialize=1, mutable=True)
        #TODO: no electricity cost included -- would be based on pump work, expected to be negligible for the time being
        self.eq_operating_cost = Constraint(expr=self.operating_cost == b_m.lime_stream.flow_mol[0]
                                                 * b_m.lime_stream.mole_frac_comp[0, "Ca(OH)2"]
                                                 * 74.093e-3 * pyunits.kg / pyunits.mol
                                                 * self.caoh2_cost
                                                 / self.caoh2_purity
                                                 * 3600 * 8760 * pyunits.s)


    # # Treatment section cost
    # self.eq_section = Constraint(expr=b_section == self.operating_cost + self.capital_cost)

def pressure_changer_costing(self, pump_type="centrifugal", section=None, cost_capacity=False):
    _make_vars(self, section)

    b_PC = self.parent_block()
    b_fs = b_PC.parent_block()
    # b_section = getattr(self, section)

    self.purchase_cost = Var()
    self.cp_cost_eq = Constraint(expr=self.purchase_cost == 0)

    if pump_type == 'High pressure':
        #TODO: add cost_capacity relationship

        # capital cost
        self.eq_capital_cost = Constraint(
            expr=self.capital_cost == b_fs.costing_param.hp_pump_cost * b_PC.work_mechanical[0] / pyunits.W)

        # operating cost
        self.eq_operating_cost = Constraint(
            expr=self.operating_cost == (b_PC.work_mechanical[0] / pyunits.W
                                         * 3600 * 24 * 365 * b_fs.costing_param.load_factor)
                 * b_fs.costing_param.electricity_cost / 3600 / 1000)
    elif pump_type == 'Low pressure':
        if cost_capacity:
            '''Ref: Bartholomew et al. (2020)-Cost optimization of high recovery single stage gap membrane distillation
            Capex=(a + b*S**n)*Fm
            S: flowrate in L/s
            a,b,n are fit params from Table S2 -- primary reference: Towler, G.; Sinnott, R. Chemical Engineering Design: Principles, Practice and 
                                                      Economics of Plant and Process Design; Elsevier, 2012.
            Fm : material factor
            '''
            self.a = Param(initialize=9052, mutable=True, units=pyunits.dimensionless)
            self.b = Param(initialize=231, mutable=True, units=pyunits.dimensionless)
            self.n = Param(initialize=0.9, mutable=True, units=pyunits.dimensionless)
            #TODO: reconsider material factor=9 for converting cost of carbon steel to titanium
            self.Fm = Param(initialize=1, mutable=True, units=pyunits.dimensionless)
            # capital cost
            self.eq_capital_cost = Constraint(
                expr=self.capital_cost == (self.a
                                           + self.b
                                           * (b_PC.control_volume.properties_in[0].flow_vol*1000) ** self.n) * self.Fm
                                           * self.cost_esc / (pyunits.m**3/pyunits.s))

        elif not cost_capacity:
            # assume fixed cost per L/s based on average of cost-capacity curve
            #TODO: adjust pump_unit_capex accordingly with material factor (convert from titanium to stainless steel)
            self.pump_unit_capex = Param(initialize=8110, mutable=True, units=pyunits.dimensionless, doc="Capex per liter/s")
            self.eq_capital_cost = Constraint(expr=self.capital_cost == self.pump_unit_capex
                                                   * b_PC.control_volume.properties_in[0].flow_vol * 1000 * self.cost_esc
                                                   / (pyunits.m**3/pyunits.s))

        # operating cost
        self.eq_operating_cost = Constraint(
            expr=self.operating_cost == (b_PC.work_mechanical[0] / pyunits.W
                                         * 3600 * 24 * 365 * b_fs.costing_param.load_factor)
                 * b_fs.costing_param.electricity_cost / 3600 / 1000)


    elif pump_type == 'Pressure exchanger':
        # capital cost
        b_cv_in = b_PC.control_volume.properties_in[0]
        self.eq_capital_cost = Constraint(
            expr=(self.capital_cost == b_fs.costing_param.pxr_cost
                    * b_cv_in.flow_vol * 3600 / (pyunits.m ** 3 / pyunits.s)))

        # operating cost
        self.operating_cost.setlb(-1e6)
        self.eq_operating_cost = Constraint(
            expr=self.operating_cost == (b_PC.work_mechanical[0] / pyunits.W
                                         * 3600 * 24 * 365 * b_fs.costing_param.load_factor)
                 * b_fs.costing_param.electricity_cost / 3600 / 1000)

    # # Treatment section cost
    # self.eq_section = Constraint(expr=b_section == self.operating_cost + self.capital_cost)
