<div style="font-family: 'Lucica Grande', Ubuntu, Arial, Verdana, sans-serif; font-size: 11pt;">
  % if object.to_invoice:
  <p>${object.partner_id.mail_salutation}, </p>   
  <p><strong>der folgende Aufwand wird in Rechnung gestellt:</strong></p>
  % endif
  <table border="1">
    <tr>
      <th>Datum</th>
      <th>Beschreibung</th>
      <th>Menge</th>
      <th>Einheit</th>
      % if object.to_invoice:
      <th>Verrechnung</th>
      % endif
    </tr>
    % for line in object.expense_alert_line_ids:
    <tr>
      <td>${formatLang(line.date,date=True)}</td>
      <td>${line.name}</td>
      <td>${formatLang(line.unit_amount)}</td>
      <td>${line.product_uom_id and line.product_uom_id.name or ''}</td>
      % if object.to_invoice:
      <td>${line.to_invoice.name}</td>
      % endif
    </tr>
    % endfor   
  </table>                       
  % if object.to_invoice:     
  <p>Mit freundlichen Grüßen</p>
  <p>${object.company_id.name}</p>
  % endif
</div>