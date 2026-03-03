# Inclure jsoncpp manuellement
include_directories(/usr/include/jsoncpp)


# Déclare le binaire
add_executable(FiveG_digital_twin
   FiveG_digital_twin.cc
   metrics-calc.cc 
   debug-functions.cc 
   
)


# Lie NS-3 et jsoncpp
target_link_libraries(FiveG_digital_twin PRIVATE ${ns3-libs} ${ns3-contrib-libs} jsoncpp)


# Active C++20 et warnings
target_compile_features(FiveG_digital_twin PRIVATE cxx_std_20)
target_compile_options(FiveG_digital_twin PRIVATE -Wall -Wextra -Wpedantic -Wno-unused-parameter)








