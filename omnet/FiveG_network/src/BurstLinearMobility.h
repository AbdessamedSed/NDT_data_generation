#ifndef __SRC_BURSTLINEARMOBILITY_H
#define __SRC_BURSTLINEARMOBILITY_H

#include "inet/mobility/single/LinearMobility.h"

namespace src {

class BurstLinearMobility : public inet::LinearMobility
{
  public:
    BurstLinearMobility() = default;

    void setSpeed(double newSpeedMps);
};

} // namespace src

#endif
