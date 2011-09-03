Runtime dynamic models with Django
==================================

This is an experimental framework, 
which attempts to handle all of the difficulties involved in employing 
dynamic models in a Django project.

It handles cross-process model class synchronisation,
Django admin (re-)registration
and eventually any other problematic task.
The main idea is to abstract and contain any intricate or complicated code,
keeping project code base clean and maintainable.
