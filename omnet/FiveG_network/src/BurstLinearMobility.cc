#include "BurstLinearMobility.h"

namespace src {

Define_Module(BurstLinearMobility);

void BurstLinearMobility::setSpeed(double newSpeedMps)
{
    // Bring the mobility state up to date before changing velocity.
    move();

    speed = newSpeedMps;
    stationary = (speed == 0.0);

    if (lastVelocity.length() > 0.0)
    {
        lastVelocity = lastVelocity.normalize() * speed;
    }
    else
    {
        // Fallback: if velocity was zero, use the configured heading.
        inet::rad heading =
            inet::deg(fmod(par("initialMovementHeading").doubleValue(), 360));

        inet::rad elevation =
            inet::deg(fmod(par("initialMovementElevation").doubleValue(), 360));

        inet::Coord direction =
            inet::Quaternion(
                inet::EulerAngles(
                    heading,
                    -elevation,
                    inet::rad(0)
                )
            ).rotate(inet::Coord::X_AXIS);

        lastVelocity = direction * speed;
    }

    lastUpdate = inet::simTime();

    emit(mobilityStateChangedSignal, this);
}

} // namespace src
