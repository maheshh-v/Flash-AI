# Business Knowledge

## Revenue
- Revenue data is stored ONLY in the `invoices` collection.
- Paid invoices represent actual revenue.
- Field name: total
- Filter condition: status = "paid"
- Must use partner ID provided in query.

## Users
- User data is stored in the `users` collection.
- Each invoice has a reference field: user

## Partners
- revenue can be filtered using partner field in invoices.

## partner id 
- partner id can be used to filter his/her full name.
- whenever partner ask his name than use hi/her partner id in query.
- partner id can be also used to filter his/her properties and virtual offices.
- partnerid can be used in coworkingspaces to filter partners own 
- partner id can be used to know properties all informations.
- when partner tells to 'count / how many' than use count, than use count



