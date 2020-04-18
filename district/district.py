# -*- coding: utf-8 -*-
#############################################################################
#
#    Copyright (c) 2007 Martin Reisenhofer <martin.reisenhofer@funkring.net>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _

class district_district(models.Model):
    _name = "district.district"
    _description = "District"
    
    name = fields.Char("Name")
    state_id = fields.Many2one("res.country.state", "State", index=True)
    country_id = fields.Many2one("res.country", "Country", index=True)

    @api.multi
    def name_get(self):
        res = []
        for district in self:
            name = []
            country = district.country_id
            country_name = country and (country.code or country.name or "")
            if country_name:
                name.append(country_name)
            state = district.state_id
            state_name = state and (state.code or state.name or "")
            if state_name:
                name.append(state_name)
            name.append(district.name)
            res.append((district.id," / ".join(name)))
                    
        return res  