See how to setup the development environment here:

https://beancount.github.io/fava/development.html

(notably, on a new environment we need to install like so: 

  pip install --editable .

)
to be able to load the extension. (otherwise plugin cannot be loaded)


Note: currently, we have fava-envelope installed in the pip environment -> this is not necessary,
as we need to override it with our local version of fava-envelope anyway.

So the steps to run our custom plugins from here are to execute:

  pip install --editable . 

in the current directory(fava-envelope)
