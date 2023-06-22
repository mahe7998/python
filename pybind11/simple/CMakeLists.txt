find_package(pybind11 CONFIG REQUIRED)

# Embed the Python interpreter into an executable
add_executable(embed embed.cpp)
target_link_libraries(embed PUBLIC pybind11::embed)