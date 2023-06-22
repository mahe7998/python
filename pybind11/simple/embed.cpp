#include  <pybind11/embed.h>
namespace py = pybind11;

int main() 
{
   py::scoped_interpreter guard{};

   py::exec("print('Engine is running!')");
   return 0;
}