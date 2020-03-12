# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


import babel
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta
from pytz import timezone

from odoo import api, fields, models, tools, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError, ValidationError


class HrContract(models.Model):
    _inherit = 'hr.contract'

    eps = fields.Char(
        string='EPS',
        help='Ingrese la EPS'
    )

    caja_compensacion = fields.Char(
        string='Caja de compensación',
        help='Aquí se debe ingresar la caja de compensación'
    )

    fondo_pension = fields.Char(
        string='Fondo de pensiones',
        help='Aquí se debe ingresar la caja de compensación'
    )

    aseguradora_riesgo = fields.Char(
        string='Nombre de aseguradora ARL',
        help='Aquí se debe diligenciar el nombre de la aseguradora'
    )

    clase_riesgo = fields.Selection(
        string='Clase de riesgo',
        selection=[('1', 'Tipo I'),
                   ('2', 'Tipo II'),
                   ('3', 'Tipo III'),
                   ('4', 'Tipo IV'),
                   ('5', 'Tipo V')]
    )

    rodamiento = fields.Monetary(
        string='Rodamiento'
    )

    porcentaje_comision = fields.Float(
        string='Porcentaje de comisión',
        help='Aquí debe ingresar el porcentaje de comisión, que será calculada en base a las ventas que ingresará en nómina.'
    )

    comision_es_prestacional = fields.Boolean(
        string='¿La comisión es prestacional?',
        help='Si la comisión es prestacional, habilite.'
    )

    bono_es_prestacional = fields.Boolean(
        string='¿El bono es prestacional?',
        help='Si el bono es prestacional, habilite.'
    )

    rodamiento_es_prestacional = fields.Boolean(
        string='¿El rodamiento es prestacional?',
        help='Si el rodamiento es prestacional, habilite.'
    )

    @api.constrains('ip_wage_rate')
    def _check_ip_wage_rate(self):
        if self.filtered(lambda contract: contract.ip_wage_rate < 0 or contract.ip_wage_rate > 100):
            raise ValidationError(
                _('The IP rate on wage should be between 0 and 100'))

    @api.depends('holidays', 'wage', 'final_yearly_costs')
    def _compute_wage_with_holidays(self):
        for contract in self:
            if contract.holidays > 20.0:
                yearly_cost = contract.final_yearly_costs * \
                    (1.0 - (contract.holidays - 20.0) / 231.0)
                contract.wage_with_holidays = contract._get_gross_from_employer_costs(
                    yearly_cost)
            else:
                contract.wage_with_holidays = contract.wage

    def _inverse_wage_with_holidays(self):
        for contract in self:
            if contract.holidays > 20.0:
                remaining_for_gross = contract.wage_with_holidays * \
                    (13.0 + 13.0 * 0.3507 + 0.92)
                yearly_cost = remaining_for_gross \
                    + 12.0 * contract.representation_fees \
                    + 12.0 * contract.fuel_card \
                    + 12.0 * contract.internet \
                    + 12.0 * (contract.mobile + contract.mobile_plus) \
                    + 12.0 * contract.transport_employer_cost \
                    + contract.warrants_cost \
                    + 220.0 * contract.meal_voucher_paid_by_employer
                contract.final_yearly_costs = yearly_cost / \
                    (1.0 - (contract.holidays - 20.0) / 231.0)
                contract.wage = contract._get_gross_from_employer_costs(
                    contract.final_yearly_costs)
            else:
                contract.wage = contract.wage_with_holidays

    @api.depends('transport_mode_car', 'transport_mode_public', 'transport_mode_others',
                 'company_car_total_depreciated_cost', 'public_transport_reimbursed_amount', 'others_reimbursed_amount')
    def _compute_transport_employer_cost(self):
        # Don't call to super has we ovewrite the method
        for contract in self:
            transport_employer_cost = 0.0
            if contract.transport_mode_car:
                transport_employer_cost += contract.company_car_total_depreciated_cost
            if contract.transport_mode_public:
                transport_employer_cost += contract.public_transport_reimbursed_amount
            if contract.transport_mode_others:
                transport_employer_cost += contract.others_reimbursed_amount
            contract.transport_employer_cost = transport_employer_cost

    @api.depends('commission_on_target')
    def _compute_warrants_cost(self):
        for contract in self:
            contract.warrants_cost = contract.commission_on_target * 1.326 / 1.05 * 12.0
            contract.warrant_value_employee = contract.commission_on_target * \
                1.326 * (1.00 - 0.535) * 12.0

    @api.depends('wage', 'fuel_card', 'representation_fees', 'transport_employer_cost',
                 'internet', 'mobile', 'mobile_plus')
    def _compute_yearly_cost_before_charges(self):
        for contract in self:
            contract.yearly_cost_before_charges = 12.0 * (
                contract.wage * (1.0 + 1.0 / 12.0) +
                contract.fuel_card +
                contract.representation_fees +
                contract.internet +
                contract.mobile +
                contract.mobile_plus +
                contract.transport_employer_cost
            )

    @api.depends('yearly_cost_before_charges', 'social_security_contributions', 'wage',
                 'social_security_contributions', 'warrants_cost', 'meal_voucher_paid_by_employer')
    def _compute_final_yearly_costs(self):
        for contract in self:
            contract.final_yearly_costs = (
                contract.yearly_cost_before_charges +
                contract.social_security_contributions +
                contract.wage * 0.92 +
                contract.warrants_cost +
                (220.0 * contract.meal_voucher_paid_by_employer)
            )

    @api.depends('holidays', 'final_yearly_costs')
    def _compute_holidays_compensation(self):
        for contract in self:
            if contract.holidays < 20:
                decrease_amount = contract.final_yearly_costs * \
                    (20.0 - contract.holidays) / 231.0
                contract.holidays_compensation = decrease_amount
            else:
                contract.holidays_compensation = 0.0

    @api.onchange('final_yearly_costs')
    def _onchange_final_yearly_costs(self):
        self.wage = self._get_gross_from_employer_costs(
            self.final_yearly_costs)

    @api.depends('meal_voucher_amount')
    def _compute_meal_voucher_paid_by_employer(self):
        for contract in self:
            contract.meal_voucher_paid_by_employer = contract.meal_voucher_amount * \
                (1 - 0.1463)

    @api.depends('wage')
    def _compute_social_security_contributions(self):
        for contract in self:
            total_wage = contract.wage * 13.0
            contract.social_security_contributions = (total_wage) * 0.3507

    @api.depends('wage')
    def _compute_ucm_insurance(self):
        for contract in self:
            contract.ucm_insurance = (contract.wage * 12.0) * 0.05

    @api.depends('public_transport_employee_amount')
    def _compute_public_transport_reimbursed_amount(self):
        for contract in self:
            contract.public_transport_reimbursed_amount = contract._get_public_transport_reimbursed_amount(
                contract.public_transport_employee_amount)

    def _get_public_transport_reimbursed_amount(self, amount):
        return amount * 0.68

    @api.depends('final_yearly_costs')
    def _compute_monthly_yearly_costs(self):
        for contract in self:
            contract.monthly_yearly_costs = contract.final_yearly_costs / 12.0

    @api.depends('wage_with_holidays')
    def _compute_holidays_advantages(self):
        for contract in self:
            contract.double_holidays = contract.wage_with_holidays * 0.92
            contract.thirteen_month = contract.wage_with_holidays

    @api.onchange('transport_mode_car', 'transport_mode_public', 'transport_mode_others')
    def _onchange_transport_mode(self):
        if not self.transport_mode_car:
            self.fuel_card = 0
            self.company_car_total_depreciated_cost = 0
        if not self.transport_mode_others:
            self.others_reimbursed_amount = 0
        if not self.transport_mode_public:
            self.public_transport_reimbursed_amount = 0

    @api.onchange('mobile', 'mobile_plus')
    def _onchange_mobile(self):
        if self.mobile_plus and not self.mobile:
            raise ValidationError(
                _('You should have a mobile subscription to select an international communication amount.'))

    def _get_internet_amount(self, has_internet):
        if has_internet:
            return self.get_attribute('internet', 'default_value')
        else:
            return 0.0

    def _get_mobile_amount(self, has_mobile, international_communication):
        if has_mobile and international_communication:
            return self.get_attribute('mobile', 'default_value') + self.get_attribute('mobile_plus', 'default_value')
        elif has_mobile:
            return self.get_attribute('mobile', 'default_value')
        else:
            return 0.0

    def _get_gross_from_employer_costs(self, yearly_cost):
        contract = self
        remaining_for_gross = yearly_cost \
            - 12.0 * contract.representation_fees \
            - 12.0 * contract.fuel_card \
            - 12.0 * contract.internet \
            - 12.0 * (contract.mobile + contract.mobile_plus) \
            - 12.0 * contract.transport_employer_cost \
            - contract.warrants_cost \
            - 220.0 * contract.meal_voucher_paid_by_employer
        gross = remaining_for_gross / (13.0 + 13.0 * 0.3507 + 0.92)
        return gross


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    spouse_fiscal_status = fields.Selection([
        ('without income', 'Without Income'),
        ('with income', 'With Income')
    ], string='Tax status for spouse', groups="hr.group_hr_user")
    disabled = fields.Boolean(
        string="Disabled", help="If the employee is declared disabled by law", groups="hr.group_hr_user")
    disabled_spouse_bool = fields.Boolean(
        string='Disabled Spouse', help='if recipient spouse is declared disabled by law', groups="hr.group_hr_user")
    disabled_children_bool = fields.Boolean(
        string='Disabled Children', help='if recipient children is/are declared disabled by law', groups="hr.group_hr_user")
    resident_bool = fields.Boolean(
        string='Nonresident', help='if recipient lives in a foreign country', groups="hr.group_hr_user")
    disabled_children_number = fields.Integer(
        'Number of disabled children', groups="hr.group_hr_user")
    dependent_children = fields.Integer(compute='_compute_dependent_children',
                                        string='Considered number of dependent children', groups="hr.group_hr_user")
    other_dependent_people = fields.Boolean(
        string="Other Dependent People", help="If other people are dependent on the employee", groups="hr.group_hr_user")
    other_senior_dependent = fields.Integer(
        '# seniors (>=65)', help="Number of seniors dependent on the employee, including the disabled ones", groups="hr.group_hr_user")
    other_disabled_senior_dependent = fields.Integer(
        '# disabled seniors (>=65)', groups="hr.group_hr_user")
    other_juniors_dependent = fields.Integer(
        '# people (<65)', help="Number of juniors dependent on the employee, including the disabled ones", groups="hr.group_hr_user")
    other_disabled_juniors_dependent = fields.Integer(
        '# disabled people (<65)', groups="hr.group_hr_user")
    dependent_seniors = fields.Integer(compute='_compute_dependent_people',
                                       string="Considered number of dependent seniors", groups="hr.group_hr_user")
    dependent_juniors = fields.Integer(compute='_compute_dependent_people',
                                       string="Considered number of dependent juniors", groups="hr.group_hr_user")
    spouse_net_revenue = fields.Float(
        string="Spouse Net Revenue", help="Own professional income, other than pensions, annuities or similar income", groups="hr.group_hr_user")
    spouse_other_net_revenue = fields.Float(string="Spouse Other Net Revenue",
                                            help='Own professional income which is exclusively composed of pensions, annuities or similar income', groups="hr.group_hr_user")

    @api.constrains('spouse_fiscal_status', 'spouse_net_revenue', 'spouse_other_net_revenue')
    def _check_spouse_revenue(self):
        for employee in self:
            if employee.spouse_fiscal_status == 'with income' and not employee.spouse_net_revenue and not employee.spouse_other_net_revenue:
                raise ValidationError(
                    _("The revenue for the spouse can't be equal to zero is the fiscal status is 'With Income'."))

    @api.onchange('spouse_fiscal_status')
    def _onchange_spouse_fiscal_status(self):
        self.spouse_net_revenue = 0.0
        self.spouse_other_net_revenue = 0.0

    @api.onchange('disabled_children_bool')
    def _onchange_disabled_children_bool(self):
        self.disabled_children_number = 0

    @api.onchange('other_dependent_people')
    def _onchange_other_dependent_people(self):
        self.other_senior_dependent = 0.0
        self.other_disabled_senior_dependent = 0.0
        self.other_juniors_dependent = 0.0
        self.other_disabled_juniors_dependent = 0.0

    @api.depends('disabled_children_bool', 'disabled_children_number', 'children')
    def _compute_dependent_children(self):
        for employee in self:
            if employee.disabled_children_bool:
                employee.dependent_children = employee.children + \
                    employee.disabled_children_number
            else:
                employee.dependent_children = employee.children

    @api.depends('other_dependent_people', 'other_senior_dependent',
                 'other_disabled_senior_dependent', 'other_juniors_dependent', 'other_disabled_juniors_dependent')
    def _compute_dependent_people(self):
        for employee in self:
            employee.dependent_seniors = employee.other_senior_dependent + \
                employee.other_disabled_senior_dependent
            employee.dependent_juniors = employee.other_juniors_dependent + \
                employee.other_disabled_juniors_dependent


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """
        @param contract: Browse record of contracts
        @return: returns a list of dict containing the input that should be applied for the given contract between date_from and date_to
        """
        res = []
        # fill only if the contract as a working schedule linked
        for contract in contracts.filtered(lambda contract: contract.resource_calendar_id):
            day_from = datetime.combine(
                fields.Date.from_string(date_from), time.min)
            day_to = datetime.combine(
                fields.Date.from_string(date_to), time.max)

            # compute leave days
            leaves = {}
            calendar = contract.resource_calendar_id
            tz = timezone(calendar.tz)
            day_leave_intervals = contract.employee_id.list_leaves(
                day_from, day_to, calendar=contract.resource_calendar_id)
            for day, hours, leave in day_leave_intervals:
                holiday = leave.holiday_id
                current_leave_struct = leaves.setdefault(holiday.holiday_status_id, {
                    'name': holiday.holiday_status_id.name or _('Global Leaves'),
                    'sequence': 5,
                    'code': holiday.holiday_status_id.name or 'GLOBAL',
                    'number_of_days': 0.0,
                    'number_of_hours': 0.0,
                    'contract_id': contract.id,
                })
                current_leave_struct['number_of_hours'] += hours
                work_hours = calendar.get_work_hours_count(
                    tz.localize(
                        datetime.combine(day, time.min)),
                    tz.localize(
                        datetime.combine(day, time.max)),
                    compute_leaves=False,
                )
                if work_hours:
                    current_leave_struct['number_of_days'] += hours / work_hours

            # compute worked days
            # work_data = contract.employee_id.get_work_days_data(
            #    day_from, day_to, calendar=contract.resource_calendar_id)
            if (date_to.day == 31) or ((date_to.day == 28 or date_to.day == 29) and date_to.month == 2):
                difference_work_days = 30 - day_from.day + 1
            else:
                difference_work_days = date_to.day - day_from.day + 1
            attendances = {
                'name': _("Días trabajados"),
                'sequence': 1,
                'code': 'DIAS_TRABAJADOS',
                'number_of_days': difference_work_days,
                'number_of_hours': difference_work_days*(240/30),
                'contract_id': contract.id,
            }
            hed = {
                'name': _("Horas extras diurnas"),
                'sequence': 1,
                'code': 'HED',
                'number_of_days': 0,
                'number_of_hours': 0,
                'contract_id': contract.id,
            }
            hen = {
                'name': _("Horas extras nocturnas"),
                'sequence': 1,
                'code': 'HEN',
                'number_of_days': 0,
                'number_of_hours': 0,
                'contract_id': contract.id,
            }
            hef = {
                'name': _("Horas extras festivas"),
                'sequence': 1,
                'code': 'HEF',
                'number_of_days': 0,
                'number_of_hours': 0,
                'contract_id': contract.id,
            }
            hefn = {
                'name': _("Horas extras festivas nocturnas"),
                'sequence': 1,
                'code': 'HEFN',
                'number_of_days': 0,
                'number_of_hours': 0,
                'contract_id': contract.id,
            }
            res.append(attendances)
            res.append(hed)
            res.append(hen)
            res.append(hef)
            res.append(hefn)
            res.extend(leaves.values())
        return res

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = []

        structure_ids = contracts.get_all_structures()
        rule_ids = self.env['hr.payroll.structure'].browse(
            structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in sorted(
            rule_ids, key=lambda x:x[1])]
        inputs = self.env['hr.salary.rule'].browse(
            sorted_rule_ids).mapped('input_ids')

        for contract in contracts:
            for input in inputs:
                input_data = {
                    'name': input.name,
                    'code': input.code,
                    'contract_id': contract.id,
                }
                res += [input_data]
            ventas = {
                'name': 'Ventas',
                'code': 'VENTAS',
                'contract_id': contract.id,
            }
            bono = {
                'name': 'Bono',
                'code': 'BONO',
                'contract_id': contract.id,
            }
            rodamiento = {
                'name': 'Rodamiento',
                'code': 'RODAMIENTO',
                'amount': contract.rodamiento,
                'contract_id': contract.id,
            }
            res.append(ventas)
            res.append(rodamiento)
            res.append(bono)
        return res
