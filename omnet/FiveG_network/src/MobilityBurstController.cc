#include <omnetpp.h>
#include "BurstLinearMobility.h"
#include <map>
#include <vector>
#include <string>
#include <algorithm>

using namespace omnetpp;

namespace src {

class MobilityBurstController : public cSimpleModule
{
  private:
    struct SpeedEvent
    {
        simtime_t time;
        int ueIndex;
        double speedMps;
    };

    std::vector<SpeedEvent> events;
    size_t nextEvent = 0;
    cMessage *timer = nullptr;

    void addEvent(double timeS, int ue, double speed)
    {
        events.push_back({SimTime(timeS), ue, speed});
    }

    void changeSpeed(int ueIndex, double speedMps)
    {

        cModule *network = getParentModule();

        if (!network)
        {
            EV_ERROR << "[BURST] Parent network not found\n";
            return;
        }

        cModule *ue = network->getSubmodule("ue", ueIndex);

        if (!ue)
        {
            EV_ERROR << "[BURST] UE " << ueIndex << " not found\n";
            return;
        }

        cModule *mobility = ue->getSubmodule("mobility");

        if (!mobility)
        {
            EV_ERROR << "[BURST] Mobility module of UE "
                     << ueIndex << " not found\n";
            return;
        }

        auto burstMobility =
            dynamic_cast<src::BurstLinearMobility *>(mobility);

        if (!burstMobility)
        {

            EV_ERROR << "[BURST] UE "
                     << ueIndex
                     << " does not use BurstLinearMobility\n";
            return;
        }

        burstMobility->setSpeed(speedMps);

        EV_INFO << "[MOBILITY-BURST] t=" << simTime()
                << " UE=" << ueIndex
                << " speed=" << speedMps << " m/s\n";

        std::cout << "[MOBILITY-BURST] t=" << simTime()
                  << " UE=" << ueIndex
                  << " speed=" << speedMps << " m/s"
                  << std::endl;
    }

    void scheduleNext()
    {
        if (nextEvent < events.size())
            scheduleAt(events[nextEvent].time, timer);
    }

  protected:
    virtual void initialize() override
    {
        /*
         * UE16:
         * normal 10 m/s
         * 100-130 s -> 30 m/s
         * 250-280 s -> 35 m/s
         * 420-450 s -> 28 m/s
         */
        addEvent(100, 16, 30);
        addEvent(130, 16, 10);
        addEvent(250, 16, 35);
        addEvent(280, 16, 10);
        addEvent(420, 16, 28);
        addEvent(450, 16, 10);

        /*
         * UE17: shifted burst periods.
         */
        addEvent(70,  17, 32);
        addEvent(100, 17, 12);
        addEvent(300, 17, 35);
        addEvent(330, 17, 12);
        addEvent(500, 17, 30);
        addEvent(530, 17, 12);

        /*
         * UE18.
         */
        addEvent(150, 18, 28);
        addEvent(180, 18, 11);
        addEvent(350, 18, 38);
        addEvent(375, 18, 11);

        /*
         * UE19.
         */
        addEvent(50,  19, 35);
        addEvent(75,  19, 14);
        addEvent(220, 19, 30);
        addEvent(250, 19, 14);
        addEvent(460, 19, 40);
        addEvent(480, 19, 14);

        std::sort(
            events.begin(),
            events.end(),
            [](const SpeedEvent& a, const SpeedEvent& b)
            {
                return a.time < b.time;
            }
        );

        timer = new cMessage("mobilityBurstTimer");

        scheduleNext();
    }

    virtual void handleMessage(cMessage *msg) override
    {
        if (msg != timer)
            return;

        const simtime_t now = simTime();

        /*
         * Several UEs may have events at exactly the same simulation time.
         */
        while (nextEvent < events.size() &&
               events[nextEvent].time == now)
        {
            const auto &e = events[nextEvent];

            changeSpeed(
                e.ueIndex,
                e.speedMps
            );

            nextEvent++;
        }

        scheduleNext();
    }

    virtual void finish() override
    {
        cancelAndDelete(timer);
        timer = nullptr;
    }

  public:
    virtual ~MobilityBurstController()
    {
        if (timer != nullptr)
            cancelAndDelete(timer);
    }
};

Define_Module(MobilityBurstController);

} // namespace src
